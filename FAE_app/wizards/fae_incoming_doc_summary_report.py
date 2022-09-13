# -*- coding: utf-8 -*-

from odoo import models, fields, api

class xFaeIncomingDocSummaryReport(models.TransientModel):
    _name = 'xfae.incoming_doc_summary_report'

    date_from = fields.Date(string='Start date', required=True)
    date_to = fields.Date(string='End date', required=True)

    def get_lines_by_tax(self, fae_docs_accept, is_service):
        if is_service:
            documents_det_lines = self.env['xfae.incoming.documents_det'].search([
                ('document_id', 'in', fae_docs_accept.ids),
                ('measurement_unit', '=', 'Os')])
        else:
            documents_det_lines = self.env['xfae.incoming.documents_det'].search(
                [('document_id', 'in', fae_docs_accept.ids),
                 ('measurement_unit', '!=', 'Os')])

        documents_det_tax_lines = self.env['xfae.incoming.documents_det_tax'].search(
            [('line_incoming_document_det_id', 'in', documents_det_lines.ids)])

        tax_percent_list = []
        tax_lines = []

        for line in documents_det_tax_lines:
            if line.rate not in tax_percent_list:
                tax_percent_list.append(line.rate)

        doc_det_processed = []
        for tax_percent in tax_percent_list:
            det_tax_lines = documents_det_tax_lines.filtered(lambda det_tax: det_tax.rate == tax_percent)

            if det_tax_lines:
                subtotal = 0
                tax_amount = 0

                for det_tax_line in det_tax_lines:
                    if det_tax_line.line_incoming_document_det_id.document_id.document_type == 'NC':
                        tax_amount -= det_tax_line.amount
                    else:
                        tax_amount += det_tax_line.amount

                    if det_tax_line.line_incoming_document_det_id.id not in doc_det_processed:
                        if det_tax_line.line_incoming_document_det_id.document_id.document_type == 'NC':
                            subtotal -= det_tax_line.line_incoming_document_det_id.subtotal
                        else:
                            subtotal += det_tax_line.line_incoming_document_det_id.subtotal

                        doc_det_processed.append(det_tax_line.line_incoming_document_det_id.id)

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
        fae_docs = self.env['xfae.incoming.documents'].search([('bill_date', '>=', date_from), ('bill_date', '<=', date_to),
                                                               ('response_state', '!=', '2'),
                                                               ('company_id', 'in', self.env.companies.ids)
                                                               ], order="bill_date desc, issuer_name asc")
        doc_lines = []

        fae_docs_accept = fae_docs.filtered(lambda fae_doc: not fae_doc.code_accept or fae_doc.code_accept not in ['D','R'])

        for doc in fae_docs_accept:
            subtotal = doc.amount_total - doc.amount_tax
            if doc.document_type == 'NC':
                amount_total = -doc.amount_total
                amount_tax = -doc.amount_tax
                subtotal = -subtotal
            else:
                amount_total = doc.amount_total
                amount_tax = doc.amount_tax

            data = {
                'tid': doc.identification_type_id.code,
                'identification': doc.issuer_identification_num,
                'supplier_name': doc.issuer_name,
                'sequence': doc.issuer_sequence,
                'issue_date': doc.bill_date,
                'accept': doc.code_accept,
                'subtotal': subtotal,
                'tax': amount_tax,
                'total': amount_total,
            }
            doc_lines.append(data)

        lines_not_services = self.get_lines_by_tax(fae_docs_accept, is_service=False)
        lines_services = self.get_lines_by_tax(fae_docs_accept, is_service=True)

        datas = {
            'ids': [],
            'model': 'xfae.incoming.documents',
            'from_day': from_day,
            'from_month': from_month,
            'from_year': from_year,
            'to_day': to_day,
            'to_month': to_month,
            'to_year': to_year,
            'lines_not_services': lines_not_services,
            'lines_services': lines_services,
            'doc_lines': doc_lines,
            'fae_docs_accept': fae_docs_accept.ids,
        }

        return self.env.ref('FAE_app.action_fae_doc').report_action(fae_docs, data=datas)
