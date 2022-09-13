# -*- coding: utf-8 -*-

from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
from odoo.tools import float_round, float_compare
import datetime
import logging

_logger = logging.getLogger(__name__)


class invoices_report_wizard(models.TransientModel):
    _name = 'xfae.invoices.report.wizard'

    date_from = fields.Date(string='Start date', required=True)
    date_to = fields.Date(string='End date', required=True)
    write_log_info = fields.Boolean(string='Write Debug Info', default=False)

    def get_lines_by_tax(self, economic_activity, pos_orders_tax_data, moves_tax_data):
        lines_goods = []
        lines_services = []
        tax_percent_list = []
        economic_activity_id = economic_activity.get('id')
        if pos_orders_tax_data:
            pos_orders_tax = pos_orders_tax_data.filtered(lambda r: r.company_id.x_economic_activity_id.id == economic_activity_id)
        else:
            pos_orders_tax = []
        moves_tax = moves_tax_data.filtered(lambda r: r.x_economic_activity_id.id == economic_activity_id)

        account_move_lines = self.env['account.move.line'].search([('move_id', 'in', moves_tax.ids)])
        for line in account_move_lines:
            for tax in line.tax_ids:
                if tax.amount not in tax_percent_list:
                    tax_percent_list.append(tax.amount)

        if pos_orders_tax:
            pos_order_lines = self.env['pos.order.line'].search([('order_id', 'in', pos_orders_tax.ids)])
            for line in pos_order_lines:
                for tax in line.tax_ids:
                    if tax.amount not in tax_percent_list:
                        tax_percent_list.append(tax.amount)

        # Agrega un -1 para buscar movimientos que no tengan tax_ids
        tax_percent_list.append(None)

        if self.write_log_info:
            # títulos para los datos de debug
            _logger.info('>> Actividad Económica: id: %s  code: %s', economic_activity.get('id'), economic_activity.get('code'))
            _logger.info('>>: fuente:  num_doc: move_id:  line_id:  subtotal:  tax ')

        for tax_percent_item in tax_percent_list:
            pos_order_lines_taxes = []
            if tax_percent_item is None:
                tax_percent = 0
                if pos_orders_tax:
                    pos_order_lines_taxes = self.env['pos.order.line'].search([('tax_ids', '=', False), ('order_id', 'in', pos_orders_tax.ids)])
                account_moves_lines_taxes = self.env['account.move.line'].search([('exclude_from_invoice_tab', '=', False),
                                                                                  ('tax_ids', '=', False), ('move_id', 'in', moves_tax.ids)])
            else:
                tax_percent = tax_percent_item
                tax_ids = self.env['account.tax'].search([('amount', '=', tax_percent)]).ids
                if pos_orders_tax:
                    pos_order_lines_taxes = self.env['pos.order.line'].search([('tax_ids', 'in', tax_ids), ('order_id', 'in', pos_orders_tax.ids)])
                account_moves_lines_taxes = self.env['account.move.line'].search([('tax_ids', 'in', tax_ids), ('move_id', 'in', moves_tax.ids)])

            # [goods, services]
            types_processed = [0, 0]
            subtotal_dol = [0, 0]
            subtotal = [0, 0]
            tax_amount = [0, 0]

            # procesa lineas de Pos Order
            lines_processed = [[], []]
            for pos_order_line_tax in pos_order_lines_taxes:
                ind = 0 if pos_order_line_tax.product_id.product_tmpl_id.type != 'service' else 1
                factor_tc = pos_order_line_tax.order_id.x_currency_rate if pos_order_line_tax.order_id.currency_id.name == 'USD' else 1

                # POS odoo - tiene un manejo de impuesto diferente a facturación
                tax_amount_line = float_round((pos_order_line_tax.price_subtotal_incl - pos_order_line_tax.price_subtotal) * factor_tc, precision_digits=5)
                types_processed[ind] += 1
                if pos_order_line_tax.id not in lines_processed[ind]:
                    if self.write_log_info:
                        # _logger.info('>>: fuente:  num_doc: move_id:  line_id:  subtotal:  tax ')
                        _logger.info('>>: pos_order:  %s: %s: %s: %s: %s', pos_order_line_tax.order_id.x_sequence,
                                     pos_order_line_tax.order_id.id, pos_order_line_tax.id, pos_order_line_tax.price_subtotal, round(tax_amount_line, 2))
                    tax_amount[ind] += tax_amount_line
                    if pos_order_line_tax.order_id.currency_id.name == 'USD':
                        subtotal_dol[ind] += pos_order_line_tax.price_subtotal
                        subtotal[ind] += float_round(pos_order_line_tax.price_subtotal * factor_tc, precision_digits=5)
                    else:
                        subtotal[ind] += pos_order_line_tax.price_subtotal
                lines_processed[ind].append(pos_order_line_tax.id)

            # procesa lineas de Account Move
            lines_processed = [[], []]
            for account_move_lines_tax in account_moves_lines_taxes:
                signo = -1 if account_move_lines_tax.move_id.move_type == 'out_refund' else 1

                ind = 0 if account_move_lines_tax.product_id.product_tmpl_id.type != 'service' else 1
                factor_tc = account_move_lines_tax.move_id.x_currency_rate if account_move_lines_tax.move_id.currency_id.name == 'USD' else 1

                tax_amount_line = float_round(((account_move_lines_tax.price_subtotal * tax_percent) / 100) * factor_tc, precision_digits=5) * signo
                tax_amount[ind] += tax_amount_line
                types_processed[ind] += 1
                if account_move_lines_tax.id not in lines_processed[ind]:
                    if self.write_log_info:
                        # _logger.info('>>: fuente: num_doc:  move_id:  :line_id:  :subtotal:  :tax ')
                        _logger.info('>>: account_move: %s: %s: %s: %s: %s', account_move_lines_tax.move_id.x_sequence,
                                     account_move_lines_tax.move_id.id, account_move_lines_tax.id, account_move_lines_tax.price_subtotal,
                                     round(tax_amount_line, 2))
                    if account_move_lines_tax.move_id.currency_id.name == 'USD':
                        subtotal_dol[ind] += account_move_lines_tax.price_subtotal * signo
                        subtotal[ind] += float_round(account_move_lines_tax.price_subtotal * factor_tc, precision_digits=5) * signo
                    else:
                        subtotal[ind] += account_move_lines_tax.price_subtotal * signo
                lines_processed[ind].append(account_move_lines_tax.id)

            # líneas de bienes
            total = subtotal[0] + tax_amount[0]
            if types_processed[0] > 0 and total != 0:
                lines_goods.append({
                        'ae': economic_activity,
                        'tax_percent': tax_percent_item,
                        'subtotal_dol': subtotal_dol[0],
                        'subtotal': subtotal[0],
                        'tax_amount': tax_amount[0],
                        'total': total
                    })

            # líneas de servicios
            total = subtotal[1] + tax_amount[1]
            if types_processed[1] > 0 and total != 0:
                lines_services.append({
                        'ae': economic_activity,
                        'tax_percent': tax_percent_item,
                        'subtotal_dol': subtotal_dol[1],
                        'subtotal': subtotal[1],
                        'tax_amount': tax_amount[1],
                        'total': total
                    })

        return lines_goods, lines_services

    def print_report(self):
        self.ensure_one()
        [data] = self.read()

        from_day = self.date_from.day
        from_year = self.date_from.year
        from_month = ''
        if 1 <= self.date_from.month <= 12:
            from_month = ('', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Setiembre', 'Octubre', 'Noviembre', 'Diciembre')[
                self.date_from.month]

        to_day = self.date_to.day
        to_year = self.date_to.year
        to_month = ''
        if 1 <= self.date_to.month <= 12:
            to_month = ('', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Setiembre', 'Octubre', 'Noviembre', 'Diciembre')[
                self.date_to.month]

        date_from = self.date_from
        date_to = self.date_to

        # _logger.info('>> fae_invoice_summary_report.account_move: search account_move.  %s ', datetime.date.today())
        account_moves = self.env['account.move'].search([('state', '!=', 'draft'), ('invoice_date', '>=', date_from),
                                                         ('invoice_date', '<', date_to + relativedelta(days=1)),
                                                         ('move_type', 'in', ('out_invoice', 'out_refund'))])

        # _logger.info('>> fae_invoice_summary_report.account_move: cargar docs.  %s ', datetime.date.today())
        docs = []
        economic_activity_list = []
        tax_economic_activity = []

        for move in account_moves:
            if move.state == 'draft':
                state = 'pend'
            elif move.state == 'cancel':
                state = 'cancel'
            else:
                state = 'apl'
            signo = 1
            if move.move_type == 'out_refund':
                move.x_document_type = 'NC'
                signo = -1
            # actividad económica
            if move.x_economic_activity_id.id not in economic_activity_list:
                economic_activity_list.append(move.x_economic_activity_id.id)
                tax_economic_activity.append(
                    {'id': move.x_economic_activity_id.id, 'code': move.x_economic_activity_id.code, 'name': move.x_economic_activity_id.name})
            #
            if self.write_log_info and move.currency_id.name == 'USD':
                _logger.info('>> Moneda: %s  tc: %s', move.currency_id.name, move.x_currency_rate)

            docs.append({
                'origen': 'F',
                'currency': move.currency_id.name,
                'id': move.id,
                'internal_ref': move.name,
                'state': state,
                'td': move.x_document_type,
                'sequence': move.x_sequence,
                'num_doc': (move.x_document_type or '_') + ' ' + (move.x_sequence or ' '),
                'ae': move.x_economic_activity_id.code,
                'state_dgt': {'1': 'A', '2': 'Re'}.get(move.x_state_dgt, (move.x_state_dgt or ' ').lower()),
                'date': move.invoice_date,
                'issue_date': move.x_issue_date,
                'partner': move.partner_id.name,
                'currency_name': move.currency_id.name,
                'currency_symbol': move.currency_id.symbol,
                'currency_rate': move.x_currency_rate,
                'amount_tax': move.amount_tax * signo,
                'amount_total': move.amount_total * signo,
            })

        # _logger.info('>> fae_invoice_summary_report.account_move: filtrar docs tax - electronicos.  %s ', datetime.date.today())
        account_moves_tax = account_moves.filtered(lambda r: move.state != 'cancel'
                                                             and r.x_state_dgt == '1'
                                                             and r.x_sequence)

        account_moves_tax_not_fae = account_moves.filtered(lambda r: r.state != 'cancel'
                                                                     and not r.x_sequence
                                                                     and not r.x_state_dgt)

        account_moves_canceled = account_moves.filtered(lambda r: r.state == 'cancel'
                                                                  and r.x_sequence)

        pos_orders_tax = []
        pos_orders_tax_not_fae = []
        pos_orders_canceled = []

        # verifica si POS está instalada
        modulo = self.env['ir.module.module'].search([('name', '=', 'pos_extensionfe')])
        if modulo and modulo.state == 'installed':
            # _logger.info('>> fae_invoice_summary_report.pos_order: search pos_order.  %s ', datetime.date.today())
            pos_orders = self.env['pos.order'].search([('state', '!=', 'draft'), ('date_order', '>=', date_from),
                                                       ('date_order', '<', date_to + relativedelta(days=1)),
                                                       ('x_move_id', 'not in', account_moves.ids)])
            for move in pos_orders:
                if move.state == 'draft':
                    state = 'pend'
                elif move.state == 'cancel':
                    state = 'cancel'
                else:
                    state = 'apl'
                # actividad económica
                if move.company_id.x_economic_activity_id.id not in economic_activity_list:
                    economic_activity_list.append(move.company_id.x_economic_activity_id.id)
                    tax_economic_activity.append({'id': move.company_id.x_economic_activity_id.id, 'code': move.company_id.x_economic_activity_id.code
                                                     , 'name': move.company_id.x_economic_activity_id.name})
                #
                docs.append({
                    'origen': 'P',
                    'currency': move.currency_id.name,
                    'id': move.id,
                    'internal_ref': move.name,
                    'state': state,
                    'td': move.x_document_type,
                    'sequence': move.x_sequence,
                    'num_doc': (move.x_document_type or '_') + ' ' + (move.x_sequence or ' '),
                    'ae': move.company_id.x_economic_activity_id.code,
                    'state_dgt': {'1': 'A', '2': 'Re'}.get(move.x_state_dgt, (move.x_state_dgt or ' ').lower()),
                    'date': move.date_order,
                    'issue_date': move.x_issue_date,
                    'partner': move.x_name_to_print[:25] if move.x_name_to_print
                                                         else move.partner_id.name[:25] if move.partner_id
                                                         else 'Sin nombre',
                    'currency_name': move.currency_id.name,
                    'currency_symbol': move.currency_id.symbol,
                    'currency_rate': move.x_currency_rate,
                    'amount_tax': move.amount_tax,
                    'amount_total': move.amount_total,
                })
            pos_orders_tax = pos_orders.filtered(lambda r: r.state != 'cancel'
                                                           and r.x_state_dgt == '1'
                                                           and r.x_sequence)

            pos_orders_tax_not_fae = pos_orders.filtered(lambda r: r.state != 'cancel'
                                                                   and not r.x_sequence
                                                                   and not r.x_state_dgt)

            pos_orders_canceled = pos_orders.filtered(lambda r: r.state == 'cancel')

        # Calcular resumen de IVA
        # _logger.info('>> fae_invoice_summary_report: Cálcula resumen de líneas.  %s ', datetime.date.today())
        tax_lines_summary_ae = []
        for economic_activity in tax_economic_activity:
            lines_goods_with_doc, lines_services_with_doc = self.get_lines_by_tax(economic_activity, pos_orders_tax, account_moves_tax)
            lines_goods_not_doc, lines_services_not_doc = self.get_lines_by_tax(economic_activity, pos_orders_tax_not_fae, account_moves_tax_not_fae)
            lines_goods_canceled, lines_services_canceled = self.get_lines_by_tax(economic_activity, pos_orders_canceled, account_moves_canceled)
            if (lines_goods_with_doc or lines_services_with_doc
                or lines_goods_not_doc or lines_services_not_doc or lines_goods_canceled or lines_services_canceled):
                tax_lines_summary_ae.append({
                    'ae': economic_activity,
                    'lines_gppds_with_doc': lines_goods_with_doc,
                    'lines_services_with_doc': lines_services_with_doc,
                    'lines_gppds_not_doc': lines_goods_not_doc,
                    'lines_services_not_doc': lines_services_not_doc,
                    'lines_gppds_canceled': lines_goods_canceled,
                    'lines_services_canceled': lines_services_canceled,
                    })
        #
        list_docs = sorted(docs, key=lambda r: (r.get('currency'), r.get('td') or '_', r.get('sequence') or str(r.get('id'))))

        datas = {
            'ids': [],
            'model': 'pos.order',
            'from_day': from_day,
            'from_month': from_month,
            'from_year': from_year,
            'to_day': to_day,
            'to_month': to_month,
            'to_year': to_year,
            'tax_lines_summary': tax_lines_summary_ae,
            'list_docs': list_docs,
        }

        return self.env.ref('FAE_app.action_invoices').report_action(account_moves, data=datas)
