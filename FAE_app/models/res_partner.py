# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta, datetime
import phonenumbers
import logging
from . import fae_utiles
from odoo.tools import float_compare


_logger = logging.getLogger(__name__)


class PartnerElectronic(models.Model):
    _inherit = "res.partner"

    x_identification_type_id = fields.Many2one("xidentification.type", string="Tipo Identificación", required=False)
    x_commercial_name = fields.Char(string="Nombre Comercial", size=80, )
    x_country_county_id = fields.Many2one("xcountry.county", string="Cantón", required=False, )
    x_country_district_id = fields.Many2one("xcountry.district", string="Distrito", required=False, )

    x_economic_activity_id = fields.Many2one("xeconomic.activity", string="Actividad Económica", required=False, context={'active_test': False})

    x_email_fae = fields.Char(string="Email FAE", 
                              help='Correo exclusivo para enviar los documentos Electrónicos. Si está en blanco se envian al email registrado' )
    x_payment_method_id = fields.Many2one("xpayment.method", string="Método de Pago", required=False, )

    x_foreign_partner = fields.Boolean(string="Contacto del Exterior", required=False,
                                        help='Indica si el contacto es del exterior, por lo que las facturas son de tipo Exportación')

    x_special_tax_type = fields.Selection(string="Tipo Posición Fiscal",
                                            selection=[('E', 'Exonerado'),
                                                        ('R', 'Reducido')], 
                                        help='Indica si al cliente requiere un cálculo de impuesto especial (posición fiscal)' )

    x_exo_has_exoneration = fields.Boolean(string="Exonerado", required=False)
    x_exo_modality = fields.Selection(string="Tipo",
                                        selection=[('T', 'Exonera Todos los productos'),
                                                   ('M', 'Exoneración por CAByS')],
                                        default='T',
                                        copy=False)
    x_exo_type_exoneration = fields.Many2one("xexo.authorization", string="Tipo Exoneración", required=False, )
    x_exo_exoneration_number = fields.Char(string="número exoneración", size=40, required=False, )
    x_exo_institution_name = fields.Char(string="Nombre Institución", size=160, required=False, 
                                        help='Nombre de la Institución que emitió la exoneración' )

    x_exo_date_issue = fields.Datetime(string="Fecha Hora Emisión", required=False, )
    x_exo_date_expiration = fields.Datetime(string="Fecha Expiración", required=False, )
    x_exoneration_lines = fields.One2many(string='Exoneraciones',
                                         comodel_name='xpartner.exoneration',
                                         inverse_name='partner_id',
                                         context={'active_test': False},
                                         copy=False, )

    @api.onchange('x_identification_type_id', 'vat')
    def _onchange_identification_vat(self):
        if self.x_identification_type_id and self.vat:
            self.vat = self.vat.replace('-','').replace(' ','')
            error_msg = fae_utiles.val_identification_vat(self.x_identification_type_id.code, self.vat)
            if error_msg:
                raise UserError(error_msg)             
            partner_id = self.env['res.partner'].search([('x_identification_type_id','=',self.x_identification_type_id.id), ('vat','=',self.vat), ('id','!=',self._origin.id)], limit=1)
            if partner_id:
                raise UserError('Ya existe un cliente (%s) con la identificación : %s' % (partner_id.name, self.vat))

    @api.onchange('phone')
    def _onchange_phone(self):
        if self.phone:
            parsed = phonenumbers.parse(self.phone, self.country_id and self.country_id.code or 'CR')
            if not phonenumbers.is_possible_number(parsed):
                alert = {'title': 'Atención', 'message': 'Número de teléfono  parece incorrecto' }
                return {'value': {'phone': ''}, 'warning': alert}

    @api.onchange('mobile')
    def _onchange_mobile(self):
        if self.mobile:
            parsed = phonenumbers.parse(self.mobile, self.country_id and self.country_id.code or 'CR')
            if not phonenumbers.is_possible_number(parsed):
                alert = {'title': 'Atención', 'message': 'Número de teléfono parece incorrecto' }
                return {'value': {'mobile': ''}, 'warning': alert}

    @api.onchange('email')
    def _onchange_email(self):
        if self.email:
            if not re.match(r'^(\s?[^\s,]+@[^\s,]+\.[^\s,]+\s?,)*(\s?[^\s,]+@[^\s,]+\.[^\s,]+)$', self.email.lower()):
                vals = {'email': False}
                alerta = { 'title': 'Atención',
                           'message': 'El correo electrónico no cumple con una estructura válida. ' + str(self.email)
                          }
                return {'value': vals, 'warning': alerta}

    @api.onchange('x_email_fae')
    def _onchange_x_email_fae(self):
        if self.x_email_fae:
            if not re.match(r'^(\s?[^\s,]+@[^\s,]+\.[^\s,]+\s?,)*(\s?[^\s,]+@[^\s,]+\.[^\s,]+)$', self.x_email_fae.lower()):
                vals = {'x_email_fae': False}
                alerta = { 'title': 'Atención',
                           'message': 'El correo electrónico para FAE no cumple con una estructura válida. ' + str(self.x_email_fae)
                          }
                return {'value': vals, 'warning': alerta}

    @api.onchange('x_exo_modality')
    def _onchange_x_exo_modality(self):
        if self.x_exo_modality == 'M':
            self.property_account_position_id = None

    # Se dicidió no traer los datos en el onchange porque las exoneraciones por leyes especiales no son aceptados
    # por la página de consulta de exoneracione
    def action_get_economic_activities(self):
        if self.vat:
            json_response = fae_utiles.get_economic_activities(self)

            if json_response["status"] == 200:
                activities_codes = list()
                activities = json_response["activities"]
                for activity in activities:
                    if activity["estado"] == "A":
                        activities_codes.append(activity["codigo"])

                economic_activities = self.env['xeconomic.activity'].with_context(active_test=False).search([('code', 'in', activities_codes)], limit=1)
                if economic_activities:
                    self.x_economic_activity_id = economic_activities.id

            else:
                alert = { 'title': json_response["status"], 'message': json_response["text"] }
                return {'value': {'vat': ''}, 'warning': alert}

    def action_get_exoneration_data(self):
        res = {}
        if not self.x_exo_exoneration_number:
            return

        json_response = fae_utiles.get_exoneration_info(self.env, self.x_exo_exoneration_number)
        exo_number = self.x_exo_exoneration_number

        if json_response["status"] == 200:
            if json_response['identificacion'] != self.vat:
                raise ValidationError('La identificación de la exoneración: %s es diferente a la del contacto' % (json_response['identificacion']))

            self.x_exo_has_exoneration = True
            if json_response['poseeCabys']:
                # si posee CAByS entonces debe registrarse en la tabla donde se manejan multiples exoneraciones
                vals = {'exoneration_number': exo_number,
                        'institution_name': json_response["nombreInstitucion"],
                        'date_issue': json_response['fechaEmision'],
                        'date_expiration': json_response['fechaVencimiento'],
                        'exoneration_rate': json_response['porcentajeExoneracion'],
                        'account_tax_id': json_response["tax_id"],
                        'has_cabys': True,
                        'cabys_list': json_response["cabys"],
                        'partner_id': self.id,
                        'active': True,
                        }
                s1 = set(json_response["cabys"].split(', '))
                exo_line = ''
                for line in self.x_exoneration_lines:
                    if line.exoneration_number == exo_number:
                        s2 = set(line.cabys_list.split(', '))
                        if len(s1.symmetric_difference(s2)) == 0:
                            exo_line = line     # las lista de CAByS es exactamente igual por lo que actualiza los datos del registro existente

                if exo_line:
                    # res = exo_line.write(vals)
                    exo_line.write(vals)
                else:
                    # res =
                    self.env['xpartner.exoneration'].sudo().create(vals)
                self.x_exo_exoneration_number = None
                self.property_account_position_id = None
                self.x_exo_modality = 'M'
            else:
                self.x_exo_type_exoneration = json_response['exoAuthorization_id']
                self.x_exo_institution_name = json_response['nombreInstitucion']
                self.x_exo_date_issue = datetime.strptime(json_response['fechaEmision'], "%Y-%m-%dT%H:%M:%S") or None
                self.x_exo_date_expiration = datetime.strptime(json_response['fechaVencimiento'], "%Y-%m-%dT%H:%M:%S") or None
        else:
            res = {'warning': {'title': json_response["status"], 'message': json_response["text"]}}
        return res

    def get_exoneration_by_cabys(self, fecha, cabys_id):
        exoneration = None
        if cabys_id:
            exo_lines = self.x_exoneration_lines.filtered(lambda exo: exo.active and exo.account_tax_id
                                                                and exo.date_issue.date() <= fecha <= (
                                                                                    exo.date_expiration and exo.date_expiration.date() or fecha))
            if exo_lines:
                exo_lines = exo_lines.sorted(key=lambda r: r.date_issue, reverse=True)
                for exo_line in exo_lines:
                    if exo_line.cabys_list and cabys_id.code in exo_line.cabys_list:
                        exoneration = exo_line
                        break
        return exoneration


class PartnerExoneration(models.Model):
    _name = "xpartner.exoneration"
    _description = 'Exoneration for partner'
    _rec_name = "exoneration_number"

    partner_id = fields.Many2one("res.partner", string="Cliente")
    type_exoneration = fields.Many2one("xexo.authorization", string="Tipo Exoneración", required=True )
    exoneration_number = fields.Char(string="Núm.Exoneración", size=40, required=True, )
    institution_name = fields.Char(string="Nombre Institución", size=160,
                                    help='Nombre de la Institución que emitió la exoneración' )
    date_issue = fields.Datetime(string="Fecha Hora Emisión" )
    date_expiration = fields.Datetime(string="Fecha Expiración" )
    # fiscal_position_id = fields.Many2one("account.fiscal.position", string='Fiscal Position')
    exoneration_rate = fields.Float(string="% Exoneración", digits=(5, 2), )
    account_tax_id = fields.Many2one('account.tax', string='Cód.Impuesto', )
    has_cabys = fields.Boolean(string="Posee CAByS", default=False, )
    cabys_list = fields.Char(string="Lista de CAByS")
    active = fields.Boolean(string="Activo", default=True, required=True)

    @api.onchange('exoneration_number')
    def _onchange_exoneration_number(self):
        res = {}
        if self.exoneration_number:
            res = self.action_get_exoneration_data()
        return res

    @api.onchange('account_tax_id')
    def _onchange_account_tax_id(self):
        if self.account_tax_id:
            if float_compare(self.account_tax_id.x_exoneration_rate, self.exoneration_rate, precision_digits=2) != 0:
                raise ValidationError('El porcentaje de la exoneración %s es diferente al configurado  en el impuesto')

    def action_get_exoneration_data(self):
        if not self.exoneration_number:
            return
        json_response = fae_utiles.get_exoneration_info(self.env, self.exoneration_number)
        if json_response["status"] == 200:
            if json_response['identificacion'] != self.partner_id.vat:
                raise ValidationError('La identificación de la exoneración: %s es diferente a la del contacto' % (json_response['identificacion']))
            if not json_response['poseeCabys']:
                raise ValidationError('La exoneración se trata de una exoneración para todos los productos y servicios')

            self.type_exoneration = json_response['exoAuthorization_id']
            self.institution_name = json_response["nombreInstitucion"]
            self.date_issue = json_response['fechaEmision']
            self.date_expiration = json_response['fechaVencimiento']
            self.exoneration_rate = json_response['porcentajeExoneracion']
            self.account_tax_id = json_response["tax_id"]
            self.has_cabys = json_response["poseeCabys"]
            self.cabys_list = json_response["cabys"]

        else:
            return {'warning': {'title': json_response["status"], 'message': json_response["text"]}}
