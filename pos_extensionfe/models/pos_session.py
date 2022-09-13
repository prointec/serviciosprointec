# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

from odoo.exceptions import Warning, UserError, ValidationError

from collections import defaultdict

class PosSessionInherit(models.Model):
    _inherit = 'pos.session'

    x_employee_id = fields.Many2one('hr.employee', string='Cajero', index=True)

    x_cash_register_total_cash_payments = fields.Monetary(
        compute='_compute_cash_balance',
        string="+ Cash payments",
        help="Total of cash payments",
        readonly=True)
    x_cash_register_cashier_moves = fields.Monetary(
        compute='_compute_cash_balance',
        string='+ Cash in/out',
        help="In/Out movements of cash",
        readonly=True)

    x_cashbox_id = fields.Many2one('account.bank.statement.cashbox', related='cash_register_id.cashbox_end_id',
                                   store=True)

    x_notes = fields.Text(string="Observaciones", copy=False, required=False, )

    # override este método para no considere las sessiones que están en closing_control
    @api.constrains('config_id')
    def _check_pos_config(self):
        if self.search_count([
                ('state', 'not in', ('closing_control','closed')),
                ('config_id', '=', self.config_id.id),
                ('rescue', '=', False)]) > 1:
            raise ValidationError(_("Another session is already opened for this point of sale."))

    @api.depends('payment_method_ids', 'order_ids', 'cash_register_balance_start', 'cash_register_id')
    def _compute_cash_balance(self):
        for session in self:
            # session.x_cash_register_cashier_moves = sum( l.amount for l in session.line_ids)
            session.x_cash_register_cashier_moves = sum( session.cash_register_id.mapped('line_ids').filtered(lambda r: r.x_source == 'cash_io').mapped('amount'))
            # cash_payment_method = session.payment_method_ids.filtered('is_cash_count')[:1]
            cash_payment_method_ids = session.payment_method_ids.filtered(lambda r: r.is_cash_count
                                                                                and (not r.x_payment_method_id or r.x_payment_method_id.code == '01'))
            if cash_payment_method_ids:
                total_cash_payment = 0.0
                for cash_payment_method in cash_payment_method_ids:
                    total_cash_payment += sum(session.order_ids.mapped('payment_ids').filtered(lambda payment: payment.payment_method_id == cash_payment_method).mapped('amount'))
                session.cash_register_total_entry_encoding = session.cash_register_id.total_entry_encoding + (
                    0.0 if session.state == 'closed' else total_cash_payment
                )
                session.cash_register_balance_end = session.cash_register_balance_start + session.cash_register_total_entry_encoding
                session.cash_register_difference = session.cash_register_balance_end_real - session.cash_register_balance_end
                session.x_cash_register_total_cash_payments = total_cash_payment or 0
                # session.x_cash_register_cashier_moves = session.cash_register_id.total_entry_encoding
            else:
                session.cash_register_total_entry_encoding = 0.0
                session.cash_register_balance_end = 0.0
                session.cash_register_difference = 0.0
                session.x_cash_register_total_cash_payments = 0.0
            if not session.x_cash_register_cashier_moves:
                session.x_cash_register_cashier_moves = 0.0

    def _check_if_no_draft_orders(self):
        draft_orders = self.order_ids.filtered(lambda order: order.state == 'draft' and not order.x_is_partial)
        if draft_orders:
            raise UserError(_(
                    'There are still orders in draft state in the session. '
                    'Pay or cancel the following orders to validate the session:\n%s'
                ) % ', '.join(draft_orders.mapped('name'))
            )
        return True

    # comparar contra el original de odoo a ver si tiene cambios
    def action_pos_session_validate(self):
        if self.x_employee_id:
            # la sessión pertenece a un cajero
            draft_orders = self.order_ids.filtered(lambda order: order.state == 'draft')
            sale_session = None
            for order in draft_orders:
                if not sale_session:
                    sale_session = self.env['pos.session'].search([('config_id', '=', self.config_id.id),('state','=','opened'),('x_employee_id','=', False)], order='id desc', limit=1)
                    if not sale_session:
                        raise ValidationError('Existen ordenes pendientes asociadas a la sessión y no fue posible encontrar una session de ventas disponible para asignárselas')
                order.session_id = sale_session.id
        self._check_pos_session_balance()
        return self.action_pos_session_close()

    # overwrite el método para validar si es una session de caja, mueva las ordenes draft a una sessión de ventas
    def action_pos_session_closing_control(self):
        if self.x_employee_id:
            # la sessión pertenece a un cajero
            draft_orders = self.order_ids.filtered(lambda order: order.state == 'draft')
            sale_session = None
            for order in draft_orders:
                if not sale_session:
                    sale_session = self.env['pos.session'].search([('config_id', '=', self.config_id.id),('state','=','opened'),('x_employee_id','=', False)], order='id desc', limit=1)
                    if not sale_session:
                        raise ValidationError('Existen ordenes pendientes asociadas a la sessión y no fue posible encontrar una session de ventas disponible para asignárselas')
                order.session_id = sale_session.id
        super(PosSessionInherit, self).action_pos_session_closing_control()

    def get_payments_by_method(self):
        for session in self:
            vals = []

            pos_payments = self.env['pos.payment'].search([('session_id', '=', session.id)])
            currency_ids = pos_payments.x_currency_id.ids

            for curr_id in currency_ids:
                currency = self.env['res.currency'].search([('id', '=', curr_id)])
                payments_total_by_currency = 0
                x_currency_amount_total_by_currency = 0
                payments_counter_by_currency = 0

                for payment_method in session.payment_method_ids:
                    payments_currency = pos_payments.filtered(lambda p: p.x_currency_id.id == curr_id
                                                                        and p.payment_method_id.id == payment_method.id)\
                                                                        .sorted(key=lambda p: p.id)
                    payments_total = 0
                    x_currency_amount_total = 0
                    payments_counter = 0
                    for payment in payments_currency:
                        payments_total += payment.amount
                        x_currency_amount_total += payment.x_currency_amount
                        payments_counter += 1

                    if payments_total != 0:
                        vals.append({
                            'tipo': 'payment',
                            'payment_name': payment_method.name,
                            'currency_name': currency.name,
                            'symbol': currency.symbol,
                            'total_by_currency': '',
                            'payments_counter': payments_counter,
                            'payments_total': payments_total,
                            'x_currency_amount_total': x_currency_amount_total,
                                   })

                        payments_total_by_currency += payments_total
                        x_currency_amount_total_by_currency += x_currency_amount_total
                        payments_counter_by_currency += payments_counter

                if payments_total_by_currency != 0:
                    vals.append({
                        'tipo': 'total',
                        'payment_name': payment_method.name,
                        'currency_name': currency.name,
                        'symbol': currency.symbol,
                        'total_by_currency': 'Totales:',
                        'payments_counter': payments_counter_by_currency,
                        'payments_total': payments_total_by_currency,
                        'x_currency_amount_total': x_currency_amount_total_by_currency,
                    })

            return vals

    def _accumulate_amounts(self, data):
        # Accumulate the amounts for each accounting lines group
        # Each dict maps `key` -> `amounts`, where `key` is the group key.
        # E.g. `combine_receivables` is derived from pos.payment records
        # in the self.order_ids with group key of the `payment_method_id`
        # field of the pos.payment record.
        amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0}
        tax_amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0, 'base_amount': 0.0, 'base_amount_converted': 0.0}
        split_receivables = defaultdict(amounts)
        split_receivables_cash = defaultdict(amounts)
        combine_receivables = defaultdict(amounts)
        combine_receivables_cash = defaultdict(amounts)
        invoice_receivables = defaultdict(amounts)
        sales = defaultdict(amounts)
        taxes = defaultdict(tax_amounts)
        stock_expense = defaultdict(amounts)
        stock_return = defaultdict(amounts)
        stock_output = defaultdict(amounts)
        rounding_difference = {'amount': 0.0, 'amount_converted': 0.0}
        # Track the receivable lines of the invoiced orders' account moves for reconciliation
        # These receivable lines are reconciled to the corresponding invoice receivable lines
        # of this session's move_id.
        order_account_move_receivable_lines = defaultdict(lambda: self.env['account.move.line'])    
        rounded_globally = self.company_id.tax_calculation_rounding_method == 'round_globally'
        # EXCLUYE LOS MOVIMIENTOS QUE FUERON PASADOS A CREDITO
        for order in self.order_ids.filtered(lambda o: not o.to_invoice):
            # Combine pos receivable lines
            # Separate cash payments for cash reconciliation later.
            for payment in order.payment_ids:
                amount, date = payment.amount, payment.payment_date
                if payment.payment_method_id.split_transactions:
                    if payment.payment_method_id.is_cash_count:
                        split_receivables_cash[payment] = self._update_amounts(split_receivables_cash[payment], {'amount': amount}, date)
                    else:
                        split_receivables[payment] = self._update_amounts(split_receivables[payment], {'amount': amount}, date)
                else:
                    key = payment.payment_method_id
                    if payment.payment_method_id.is_cash_count:
                        combine_receivables_cash[key] = self._update_amounts(combine_receivables_cash[key], {'amount': amount}, date)
                    else:
                        combine_receivables[key] = self._update_amounts(combine_receivables[key], {'amount': amount}, date)

            if order.is_invoiced:
                # Combine invoice receivable lines
                key = order.partner_id
                if self.config_id.cash_rounding:
                    invoice_receivables[key] = self._update_amounts(invoice_receivables[key], {'amount': order.amount_paid}, order.date_order)
                else:
                    invoice_receivables[key] = self._update_amounts(invoice_receivables[key], {'amount': order.amount_total}, order.date_order)
                # side loop to gather receivable lines by account for reconciliation
                for move_line in order.account_move.line_ids.filtered(lambda aml: aml.account_id.internal_type == 'receivable' and not aml.reconciled):
                    order_account_move_receivable_lines[move_line.account_id.id] |= move_line
            else:
                order_taxes = defaultdict(tax_amounts)
                for order_line in order.lines:
                    line = self._prepare_line(order_line)
                    # Combine sales/refund lines
                    sale_key = (
                        # account
                        line['income_account_id'],
                        # sign
                        -1 if line['amount'] < 0 else 1,
                        # for taxes
                        tuple((tax['id'], tax['account_id'], tax['tax_repartition_line_id']) for tax in line['taxes']),
                        line['base_tags'],
                    )
                    sales[sale_key] = self._update_amounts(sales[sale_key], {'amount': line['amount']}, line['date_order'])
                    # Combine tax lines
                    for tax in line['taxes']:
                        tax_key = (tax['account_id'], tax['tax_repartition_line_id'], tax['id'], tuple(tax['tag_ids']))
                        order_taxes[tax_key] = self._update_amounts(
                            order_taxes[tax_key],
                            {'amount': tax['amount'], 'base_amount': tax['base']},
                            tax['date_order'],
                            round=not rounded_globally
                        )
                for tax_key, amounts in order_taxes.items():
                    if rounded_globally:
                        amounts = self._round_amounts(amounts)
                    for amount_key, amount in amounts.items():
                        taxes[tax_key][amount_key] += amount

                if self.company_id.anglo_saxon_accounting and order.picking_ids.ids:
                    # Combine stock lines
                    stock_moves = self.env['stock.move'].sudo().search([
                        ('picking_id', 'in', order.picking_ids.ids),
                        ('company_id.anglo_saxon_accounting', '=', True),
                        ('product_id.categ_id.property_valuation', '=', 'real_time')
                    ])
                    for move in stock_moves:
                        exp_key = move.product_id._get_product_accounts()['expense']
                        out_key = move.product_id.categ_id.property_stock_account_output_categ_id
                        amount = -sum(move.sudo().stock_valuation_layer_ids.mapped('value'))
                        stock_expense[exp_key] = self._update_amounts(stock_expense[exp_key], {'amount': amount}, move.picking_id.date, force_company_currency=True)
                        if move.location_id.usage == 'customer':
                            stock_return[out_key] = self._update_amounts(stock_return[out_key], {'amount': amount}, move.picking_id.date, force_company_currency=True)
                        else:
                            stock_output[out_key] = self._update_amounts(stock_output[out_key], {'amount': amount}, move.picking_id.date, force_company_currency=True)

                if self.config_id.cash_rounding:
                    diff = order.amount_paid - order.amount_total
                    rounding_difference = self._update_amounts(rounding_difference, {'amount': diff}, order.date_order)

                # Increasing current partner's customer_rank
                partners = (order.partner_id | order.partner_id.commercial_partner_id)
                partners._increase_rank('customer_rank')

        if self.company_id.anglo_saxon_accounting:
            global_session_pickings = self.picking_ids.filtered(lambda p: not p.pos_order_id)
            if global_session_pickings:
                stock_moves = self.env['stock.move'].sudo().search([
                    ('picking_id', 'in', global_session_pickings.ids),
                    ('company_id.anglo_saxon_accounting', '=', True),
                    ('product_id.categ_id.property_valuation', '=', 'real_time'),
                ])
                for move in stock_moves:
                    exp_key = move.product_id._get_product_accounts()['expense']
                    out_key = move.product_id.categ_id.property_stock_account_output_categ_id
                    amount = -sum(move.stock_valuation_layer_ids.mapped('value'))
                    stock_expense[exp_key] = self._update_amounts(stock_expense[exp_key], {'amount': amount}, move.picking_id.date)
                    if move.location_id.usage == 'customer':
                        stock_return[out_key] = self._update_amounts(stock_return[out_key], {'amount': amount}, move.picking_id.date)
                    else:
                        stock_output[out_key] = self._update_amounts(stock_output[out_key], {'amount': amount}, move.picking_id.date)
        MoveLine = self.env['account.move.line'].with_context(check_move_validity=False)

        data.update({
            'taxes':                               taxes,
            'sales':                               sales,
            'stock_expense':                       stock_expense,
            'split_receivables':                   split_receivables,
            'combine_receivables':                 combine_receivables,
            'split_receivables_cash':              split_receivables_cash,
            'combine_receivables_cash':            combine_receivables_cash,
            'invoice_receivables':                 invoice_receivables,
            'stock_return':                        stock_return,
            'stock_output':                        stock_output,
            'order_account_move_receivable_lines': order_account_move_receivable_lines,
            'rounding_difference':                 rounding_difference,
            'MoveLine':                            MoveLine
        })
        return data


