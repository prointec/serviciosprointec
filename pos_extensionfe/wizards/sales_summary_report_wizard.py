# -*- coding: utf-8 -*-

from odoo import models, fields, api
from dateutil.relativedelta import relativedelta

class sales_report_wizard(models.TransientModel):
    _name = 'sales.report.wizard'

    date_from = fields.Date(string='Start date', required=True)
    date_to = fields.Date(string='End date', required=True)

    def get_lines_by_tax(self, pos_orders_tax, is_service):
        pos_order_lines = self.env['pos.order.line'].search([('order_id', 'in', pos_orders_tax.ids)])
        tax_percent_list = []
        tax_lines = []

        for line in pos_order_lines:
            for tax in line.tax_ids:
                if tax.amount not in tax_percent_list:
                    tax_percent_list.append(tax.amount)

        orders_processed = []
        for tax_percent in tax_percent_list:
            tax_ids = self.env['account.tax'].search([('amount', '=', tax_percent)]).ids

            if is_service:
                pos_order_lines_taxes = self.env['pos.order.line'].search(
                    [('tax_ids', 'in', tax_ids),('order_id', 'in', pos_orders_tax.ids),
                     ('product_id.product_tmpl_id.type', '=', 'service')])
            else:
                pos_order_lines_taxes = self.env['pos.order.line'].search(
                    [('tax_ids', 'in', tax_ids),('order_id', 'in', pos_orders_tax.ids),
                     ('product_id.product_tmpl_id.type', '!=', 'service')])

            if pos_order_lines_taxes:
                subtotal = 0
                tax_amount = 0

                for pos_order_line_tax in pos_order_lines_taxes:
                    tax_amount_line = (pos_order_line_tax.price_subtotal*tax_percent)/100
                    tax_amount += tax_amount_line
                    if pos_order_line_tax.id not in orders_processed:
                        subtotal += pos_order_line_tax.price_subtotal
                    orders_processed.append(pos_order_line_tax.id)

                total = subtotal + tax_amount

                data = {
                    'tax_percent': tax_percent,
                    'subtotal': subtotal,
                    'tax_amount': tax_amount,
                    'total': total
                }
                tax_lines.append(data)

        return tax_lines

    def print_report(self):
        self.ensure_one()
        [data] = self.read()

        from_day = self.date_from.day
        from_year = self.date_from.year
        from_month = ''
        if 1 <= self.date_from.month <= 12:
            from_month = ('', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Setiembre', 'Octubre', 'Noviembre', 'Diciembre')[self.date_from.month]

        to_day = self.date_to.day
        to_year = self.date_to.year
        to_month = ''
        if 1 <= self.date_to.month <= 12:
            to_month = ('', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Setiembre', 'Octubre', 'Noviembre', 'Diciembre')[self.date_to.month]

        date_from = self.date_from
        date_to = self.date_to

        pos_orders = self.env['pos.order'].search([('state', '!=', 'draft'), ('date_order', '>=', date_from), ('date_order', '<', date_to + relativedelta(days=1))])
        order_lines = []

        pos_orders_by_document = pos_orders.filtered(lambda pos_order: pos_order.state not in ['draft']).sorted(
            key=lambda r: (r.x_document_type or '_', r.x_sequence or r.id))

        for order in pos_orders_by_document:
            data = {
                'internal_ref': order.name,
                'state': order.state,
                'td': order.x_document_type,
                'sequence': order.x_sequence,
                'date': order.date_order,
                'issue_date': order.x_issue_date,
                'partner': order.x_name_to_print[:25],
                'currency_symbol': order.currency_id.symbol,
                'amount_total': order.amount_total,
            }
            order_lines.append(data)

        pos_orders_tax = pos_orders.filtered(lambda pos_order: pos_order.state not in ['cancel']
                                                               and pos_order.x_sequence
                                                               and pos_order.x_state_dgt == '1')
        pos_orders_not_doc_tax = pos_orders.filtered(lambda pos_order: pos_order.state not in ['cancel','draft']
                                                               and not pos_order.x_sequence
                                                               and not pos_order.x_state_dgt)
        pos_orders_canceled = pos_orders.filtered(lambda pos_order: pos_order.state in ['cancel'])

        lines_with_doc = self.get_lines_by_tax(pos_orders_tax, is_service=False)
        lines_not_doc = self.get_lines_by_tax(pos_orders_not_doc_tax, is_service=False)
        lines_canceled = self.get_lines_by_tax(pos_orders_canceled, is_service=False)
        lines_service_with_doc = self.get_lines_by_tax(pos_orders_tax, is_service=True)
        lines_service_not_doc = self.get_lines_by_tax(pos_orders_not_doc_tax, is_service=True)
        lines_service_canceled = self.get_lines_by_tax(pos_orders_canceled, is_service=True)

        datas = {
            'ids': [],
            'model': 'pos.order',
            'from_day': from_day,
            'from_month': from_month,
            'from_year': from_year,
            'to_day': to_day,
            'to_month': to_month,
            'to_year': to_year,
            'lines_with_doc': lines_with_doc,
            'lines_not_doc': lines_not_doc,
            'lines_canceled': lines_canceled,
            'lines_service_with_doc': lines_service_with_doc,
            'lines_service_not_doc': lines_service_not_doc,
            'lines_service_canceled': lines_service_canceled,
            'order_lines': order_lines,
            'pos_orders': pos_orders.ids,
        }

        return self.env.ref('pos_extensionfe.action_sales').report_action(pos_orders, data=datas)
