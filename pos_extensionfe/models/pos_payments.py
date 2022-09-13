# -*- coding: utf-8 -*-

from odoo import fields, models, api, _ 
from odoo.tools import float_round, float_is_zero, float_compare,  DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT

from odoo.exceptions import Warning, RedirectWarning, UserError, ValidationError

# from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class PosPaymentInherit(models.Model):
    _inherit = "pos.payment"

    x_sequence = fields.Char(string="Núm.Consecutivo", related='pos_order_id.x_sequence')
    x_currency_id = fields.Many2one('res.currency', string='Moneda de Pago', copy=False )
    x_currency_amount = fields.Monetary(digits=0, string='Pago Recibido', copy=False)
    x_exchange_rate = fields.Float(string='Tipo de Cambio', copy=False)


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    x_payment_method_id = fields.Many2one("xpayment.method", string="Método pago DGT")

    def _is_write_forbidden(self, fields):
        if self.env.user.has_group('base.group_system'):
            # para los administradores no valida si hay sessiones pendientes
            return False
        return super(PosPaymentMethod, self)._is_write_forbidden(fields)


class PosMakePayment(models.TransientModel):
    _inherit = 'pos.make.payment'

    def _default_order_total(self):
        active_id = self.env.context.get('active_id')
        if active_id:
            order = self.env['pos.order'].browse(active_id)
            return order.amount_total
        return False

    def _default_amount(self):
        order_amount = super(PosMakePayment, self)._default_amount()
        active_id = self.env.context.get('active_id')
        if active_id:
            order = self.env['pos.order'].browse(active_id)
            return order_amount + order.x_amount_return
        return False

    amount = fields.Float(digits=0, required=True, default=_default_amount)
    x_payment_return = fields.Float(string='Vuelto', digits=0)   # El vuelto
    x_order_total = fields.Float(string='Order Total', default=_default_order_total)
    x_currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id,
                                    string='Moneda de Cambio', required="1",
                                    domain="[('active', '=', True)]")
                                    # domain="[('active', '=', True), '|',()]")
                                    # domain = lambda self: [('active', '=', True), '|', ('x_exchange_type', '!=', False), ('id', '=', self.env.company.currency_id)])
    x_exchange_rate = fields.Float(string='Tipo de Cambio', copy=False)
    x_currency_amount = fields.Monetary(digits=0, string='Importe de la Moneda',
                                        required=True,
                                        default=_default_amount)
    x_pos_currency_id = fields.Many2one(related='config_id.company_id.currency_id')

    @api.onchange('x_currency_id')
    def _onchange_x_currency_id(self):
        if self.x_currency_id == self.env.company.currency_id:
            self.x_exchange_rate = 1
            self.x_currency_amount = self._default_amount()
        elif self.x_currency_id.x_exchange_rate > 0:
            self.x_exchange_rate = self.x_currency_id.x_exchange_rate
            self.x_currency_amount = float_round(self._default_amount() / self.x_exchange_rate, precision_digits=2)
        else:
            self.x_currency_amount = None
        # recalcula el monto en colones
        self._onchange_x_currency_amount()

        # determina el método de pago de efectivo correspondiente con la moneda
        if self.payment_method_id.is_cash_count:
            config = self._default_config()
            # Algunos clientes configuran varios metodos de pagos de tipo cash, entonces se ordenan por id para que cash original quede de primero
            payment_method_list = self.env['pos.payment.method'].search(
                [('id', 'in', config.payment_method_ids.ids),
                 ('company_id', '=', self.env.company.id),
                 ('is_cash_count', '=', True)], order='id')
            # se comento el siguiente linea, hasta que resolvamos lo de la cuenta
            # pos_payment_method_id = payment_method_list.filtered(lambda r: r.receivable_account_id.currency_id.id == self.x_currency_id.id)
            pos_payment_method_id = False if self.x_currency_id.name != 'USD' else payment_method_list.filtered(lambda r: '$US' in r.name.upper())
            if not pos_payment_method_id:
                # si no encontro un Efectivo con cuenta contable de moneda igual a la moneda de pago, entonces el efectivo sin moneda
                # pos_payment_method_id = payment_method_list.filtered(lambda r: not r.receivable_account_id.currency_id)
                pos_payment_method_id = payment_method_list.filtered(lambda r: '$US' not in r.name.upper())
            if pos_payment_method_id:
                # _logger.info('>> pos_payment:  pos_payument_method: %s', str(pos_payment_method_id))
                self.payment_method_id = pos_payment_method_id[0].id

    @api.onchange('x_currency_amount')
    def _onchange_x_currency_amount(self):
        if self.x_currency_amount > 0 and self.x_currency_id:
            if self.x_exchange_rate > 0:
                self.amount = float_round(self.x_currency_amount * self.x_exchange_rate, precision_digits=2)
            elif not (self.x_exchange_rate or 0):
                raise ValidationError('El tipo de cambio no puede ser 0')
            else:
                self.amount = self.x_currency_amount

    @api.onchange('amount')
    def _onchange_xpos_amount_payment(self):
        self.x_payment_return = None
        if self.amount < 0:
            self.x_payment_return = abs(self.amount)

    @api.onchange('x_payment_return')
    def _onchange_amount_payment_return(self):
        if self.x_payment_return > 0:
            self.amount = -abs(self.x_payment_return)

    def check(self):
        """Check the order:
        if the order is not paid: continue payment,
        if the order is paid print ticket.
        """
        self.ensure_one()

        order = self.env['pos.order'].browse(self.env.context.get('active_id', False))
        currency = order.currency_id
        init_data = self.read()[0]
        current_session = order.current_cashier_session()

        payment_amount = order._get_rounded_amount(init_data['amount'])        
        if order.amount_total < 0:
            # es una devolución
            payment_net = payment_amount
        else:
            # es una factura 
            amount_return = order._get_rounded_amount(order.x_amount_return)
            payment_net = payment_amount - amount_return

            if amount_return:
                applied_return = min(amount_return, payment_amount)
                order.x_amount_return -= applied_return
                cash_statement = current_session.cash_register_id
                if cash_statement.state == 'confirm':
                    raise UserError(_("You cannot put/take money in/out for a bank statement which is closed."))
                if order.name == '/':
                    order.name = order.config_id.sequence_id._next()
                values = {
                    'date': cash_statement.date,
                    'statement_id': cash_statement.id,
                    'journal_id': cash_statement.journal_id.id,
                    'amount': applied_return, 
                    'payment_ref': 'Ingreso de vuelto ' + (order.pos_reference if order.pos_reference else order.name),
                    'x_source' : 'express',
                    'x_source_id' : order.id,                
                    'ref': current_session.name + ' - ' + order.name,
                }
                account = cash_statement.journal_id.company_id.transfer_account_id
                self.env['account.bank.statement.line'].with_context(counterpart_account_id=account.id).create(values)

                if applied_return < amount_return:
                    return self.launch_payment()

        if not float_is_zero(payment_net, precision_rounding=currency.rounding):
            order.add_payment({
                'pos_order_id': order.id,
                'amount': payment_net,
                'name': init_data['payment_name'],
                'payment_method_id': init_data['payment_method_id'][0],
                'x_currency_id': init_data['x_currency_id'][0],
                'x_currency_amount': init_data['x_currency_amount'],
                'x_exchange_rate': init_data['x_exchange_rate'],
            })
        
        # si la orden está pagada totalmente termina, sino vuelve a llamar a pagos
        if order._is_pos_order_paid():
            order.session_id = current_session.id 
            return order.process_pos_order_completed()

        return self.launch_payment()

    def launch_payment(self):
        amount = self._default_amount()
        name = 'Pago'
        if amount < 0:
            name = 'VUELTO'

        return {
            'name': name,
            'view_mode': 'form',
            'res_model': 'pos.make.payment',
            'view_id': False,
            'target': 'new',
            'views': False,
            'type': 'ir.actions.act_window',
            'context': self.env.context,
        }
