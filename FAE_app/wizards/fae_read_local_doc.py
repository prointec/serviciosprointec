# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from ..models import fae_utiles
from odoo.exceptions import Warning,UserError, ValidationError
import base64


class XFaeReadLocalDoc(models.TransientModel):
    _name = 'xfae.read_local_doc'
    _description = 'Read local documents'

    xml_doc = fields.Binary(string='Documento XML', attachment=False, copy=False)
    xml_response = fields.Binary(string='Respuesta Hacienda', attachment=False, copy=False)
    pdf = fields.Binary(string='Documento PDF', attachment=False, copy=False)

    @api.model
    def create(self, vals):
        self.save_documents(vals.get('xml_doc'), vals.get('xml_response'), vals.get('pdf'))
        # Para evitar el error "Only admins can upload SVG files.", se guardan campos vacios en el modelo Transient
        vals.update({'xml_doc': None, 'xml_response': None,})
        return super(XFaeReadLocalDoc, self).create(vals)

    def page_process(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'reload', }

    def save_documents(self, doc_xml, xml_response, pdf):
        if doc_xml and xml_response:
            doc_encoded = doc_xml.encode()
            response_encoded = xml_response.encode()
            pdf_encoded = pdf.encode() if pdf else None;

            doc_decoded_value = base64.b64decode(doc_encoded.translate(None, delete=b'\r\n'), validate=True)
            response_decoded_value = base64.b64decode(response_encoded.translate(None, delete=b'\r\n'), validate=True)

            if doc_decoded_value and response_decoded_value:
                identification_types = self.env['xidentification.type'].search([])
                company = self.env['res.company'].search([])
                currencies = self.env['res.currency'].search([('name', 'in', ['CRC', 'USD'])])

                doc_vals = fae_utiles.parser_xml(identification_types, company, currencies, 'manual', doc_encoded)
                resp_vals = fae_utiles.parser_xml(identification_types, company, currencies, 'manual', response_encoded)

                clave_hacienda = doc_vals.get('issuer_electronic_code50')
                if clave_hacienda == resp_vals.get('issuer_electronic_code50'):
                    resp_vals['company_id'] = doc_vals['company_id'] or resp_vals['company_id']
                    resp_vals['identification_number'] = doc_vals['identification_number'] or resp_vals['identification_number']
                    doc_vals.update(resp_vals)
                    self.env['xfae.incoming.documents'].save_incoming_document(clave_hacienda, doc_vals, pdf_encoded)
                else:
                    raise ValidationError('La clave de hacienda del documento no coincide con el de respuesta.')

        return True
