# -*- coding: utf-8 -*-

from odoo import fields, models, _, api
from odoo.exceptions import Warning, UserError, ValidationError


class XPosReceiptLine(models.TransientModel):
    _name = 'xpos.receipt.line'
    _description = 'Relación de Abono por Factura'

    receipt = fields.Many2one('xpos.receipt', string="Abono")
    move = fields.Many2one('account.move', string="Factura")
    date = fields.Date(string="Fecha Doc")
    monto_receipt = fields.Float('Monto a abonar', default=0.00)
    to_receipt = fields.Boolean('Aplicar abono', default=False)
    amount_total_order = fields.Float(string="Monto Total", readonly=True)
    last_balance = fields.Float(string="Saldo Anterior")

    @api.onchange('monto_receipt')
    def on_change_monto_receipt(self):
        if self.monto_receipt and self.monto_receipt > self.amount_total_order:
            raise Warning('El monto a abonar no puede superar el monto total de la Orden')

    @api.onchange('move')
    def on_change_move(self):
        if self.move:
            amount_total = self.move.x_amount_total
            self.amount_total_order = float(amount_total)
            self.last_balance = float(amount_total)


class XPosReceipt(models.TransientModel):
    _name = 'xpos.receipt'
    _description = 'Invoice Receipt'

    partner_id = fields.Many2one('res.partner', string='Customer')
    date = fields.Date(required=True, index=True, copy=False, default=fields.Date.context_today)
    moves_list = fields.One2many('xpos.receipt.line', 'receipt', string="Facturas")
    cashier_session_id = fields.Char(string="Sesión del Cajero")

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.ensure_one()
        orders = self.env['account.move'].search(
            [('partner_id', '=', self.partner_id.id), ('move_type', '=', 'out_invoice'), ('amount_residual', '>', 0)],
            order='date asc')
        vals = []
        self.moves_list = [[6, 0, []]]

        if self.partner_id and orders:
            for order in orders:
                vals.append((0, 0, {
                    'move': order.id,
                    'date': order.date,
                    'monto_receipt': order.amount_residual,
                    'amount_total_order': order.amount_residual,
                    'last_balance': order.amount_residual,
                    'to_receipt': False,
                }))
        self.moves_list = vals

    def insert_receipt(self):
        self.ensure_one()
        # moves_list = self.moves_list
        moves_list = self.moves_list.filtered(lambda r: r.to_receipt and r.monto_receipt > 0 )
        if len(moves_list) <= 0:
            raise Warning('Debe seleccionar al menos una factura para poder crear el abono.')

        sale_session = self.env['pos.session'].search([('id', '=', int(self.cashier_session_id))], limit=1)
        if not sale_session:
            raise Warning('No fue posible encontrar una session de ventas abierta')

        pos_config = sale_session.config_id
        producto_abono = self.env['product.product'].search([('product_tmpl_id', '=', pos_config.x_product_receipt.id)], limit=1)

        if not producto_abono:
            raise ValidationError('No han definido en el punto de venta el producto para abono a facturas de crédito. Ver configuración del POS')
        if not sale_session.config_id.x_journal_receipt:
            raise ValidationError('No han definido en el punto de venta el Journal de abono a facturas de crédito. Ver configuración del POS')

        abono_total = 0
        moves_lines = []
        for move in moves_list:
            abono_total += move.monto_receipt
            moves_lines.append((0, 0, {
                'full_product_name': ('Abono a Factura: ' + move.move.name) or '',
                'product_id': producto_abono.id,
                'x_move_receipt': move.move.id,
                'qty': 1,
                'price_unit': move.monto_receipt,
                'price_subtotal': move.monto_receipt,
                'price_subtotal_incl': move.monto_receipt,
                'x_amount_total_line': move.monto_receipt,
                'x_last_balance': move.last_balance,
                }))

        self.env['pos.order'].create({
            'company_id': sale_session.config_id.company_id.id,
            'partner_id': moves_list[0].move.partner_id.id,
            'session_id': sale_session.id,
            'lines': moves_lines,
            'x_is_partial': False,
            'x_move_type': 'receipt',
            'x_document_type': None,
            'x_name_to_print': self.partner_id.name,
            'to_invoice': False,
            'x_pend_recalc': False,
            'amount_total': float(abono_total),
            'amount_tax': 0,
            'amount_paid': 0,
            'amount_return': 0,
            })

        return {'type': 'ir.actions.client', 'tag': 'reload', }

