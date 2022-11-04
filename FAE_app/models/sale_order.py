
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import datetime
# import pytz

import logging


_logger = logging.getLogger(__name__)


class SaleOrderInherit(models.Model):
    _inherit = "sale.order"

    x_economic_activity_id = fields.Many2one("xeconomic.activity", string="Actividad Económica", required=False,
                                             context={'active_test': True}, )

    def _prepare_invoice(self):
        vals = super(SaleOrderInherit, self)._prepare_invoice()
        if vals:
            if self.partner_id.x_foreign_partner:
                document_type = 'FEE'
            elif self.partner_id.vat:
                if ((self.partner_id.country_id and self.partner_id.country_id.code != 'CR')
                        or (self.partner_id.x_identification_type_id and self.partner_id.x_identification_type_id.code == '05')):
                    document_type = 'TE'
                else:
                    document_type = 'FE'
            else:
                document_type = 'TE'
            vals['x_economic_activity_id'] = self.x_economic_activity_id
            vals['x_document_type'] = document_type
            vals['x_from_sale'] = True
        return vals 

    @api.onchange('partner_id', 'company_id')
    def _get_economic_activities(self):
        for rec in self:
            rec.x_economic_activity_id = rec.company_id.x_economic_activity_id

    @api.onchange('partner_id')
    def _partner_changed(self):
        if (self.partner_id.x_special_tax_type == 'E' and self.partner_id.x_exo_modality == 'T'
                and not (self.partner_id.x_exo_type_exoneration and self.partner_id.x_exo_date_issue
                         and self.partner_id.x_exo_exoneration_number and self.partner_id.x_exo_institution_name)):
            raise UserError('El cliente es exonerado pero no han ingresado los datos de la exoneración')
        # recalcula lineas (si existen)
        if self.order_line and self.partner_id:
            for line in self.order_line:
                line._compute_tax_id()
                line._compute_amount()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_exoneration_id = fields.Many2one("xpartner.exoneration", string="Exoneración", required=False, )

    def _compute_tax_id(self):
        super(SaleOrderLine, self)._compute_tax_id()
        today = datetime.date.today()
        for line in self:
            tax_ids = line.tax_id
            order = line.order_id
            exoneration = None
            exonerated = False
            if order.partner_id.x_special_tax_type == 'E' and order.partner_id.x_exo_modality == 'M' and line.product_id.x_cabys_code_id:
                exoneration = order.partner_id.get_exoneration_by_cabys(today, line.product_id.x_cabys_code_id)
                if exoneration:
                    for tax in tax_ids:
                        if tax.amount > exoneration.account_tax_id.amount:
                            tax_ids -= tax  # quita el tax de la lista para agregar el nuevo
                            if exoneration.account_tax_id not in tax_ids:
                                exonerated = True
                                tax_ids = exoneration.account_tax_id
            line.x_exoneration_id = exoneration.id if exonerated and exoneration else None
            line.tax_id = tax_ids

    @api.onchange('tax_id')
    def _onchange_tax(self):
        order = self.order_id
        if not (self.product_id or self.name):
            return
        exonerated = False
        exoneration = None
        if self.tax_id:
            today = datetime.date.today()
            exoneration = order.partner_id.get_exoneration_by_cabys(today, self.product_id.x_cabys_code_id)
            tax_ids = self.tax_id
            for tax in tax_ids:
                if tax.x_has_exoneration:
                    if not order.partner_id:
                        raise ValidationError('El impuesto: %s es para exoneración pero el documento no le han definido un cliente' % tax.name)
                    if order.partner_id.x_special_tax_type != 'E':
                        raise ValidationError('El impuesto: %s es para exoneración pero el cliente no tiene definido que es exonerado, prod: %s'
                                              % (tax.name, (self.product_id and self.product_id.default_code)))
                    if order.partner_id.x_exo_modality != 'M' and not order.partner_id.property_account_position_id:
                        raise ValidationError('El impuesto: %s es para exoneración pero el cliente no tiene definido la posición fiscal' % tax.name)
                    elif order.partner_id.x_exo_modality == 'M' and not exoneration:
                        raise ValidationError('El impuesto: %s es para exoneración pero el CAByS del producto no está presente en alguna exoneración del cliente' % tax.name)
                    if exoneration:
                        if tax.id.origin != exoneration.account_tax_id.id:
                            tax_ids -= tax  # quita el tax exonerado que no corresponde con el de la exoneración
                        if exoneration.account_tax_id not in tax_ids:
                            exonerated = True
                            # tax_ids += exoneration.account_tax_id
                            tax_ids = exoneration.account_tax_id
            self.tax_id = tax_ids
        self.x_exoneration_id = exoneration.id if exonerated and exoneration else None

    def _prepare_invoice_line(self, **optional_values):
        self.ensure_one()
        res = super(SaleOrderLine, self)._prepare_invoice_line(**optional_values)
        res.update({'x_exoneration_id': self.x_exoneration_id})
        return res
