# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import Warning, UserError, ValidationError

import datetime

import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_employee_id = fields.Many2one('hr.employee', string='Vendedor', copy=True
                                    , help='Empleado que levantó la cotización')
    x_document_type = fields.Selection(string="Tipo Comprobante",
                                        selection=[('FE', 'Factura Electrónica'),
                                                ('TE', 'Tiquete Electrónico'), ],
                                       copy=False,
                                        )
    x_sent_to_pos = fields.Boolean(default=False, copy=False )
    x_date_sent_pos = fields.Datetime(string="Fecha Enviado", copy=False )
    x_pos_config_id = fields.Many2one('pos.config', string="Caja Punto Venta", copy=False)
    x_pos_order_id = fields.Many2one("pos.order", "Órden de POS", copy=False)

    @api.onchange('x_document_type')
    def _onchange_x_document_type(self):
        if self.x_document_type and not self.x_pos_config_id:
            self.x_pos_config_id = self.get_pos_config_by_user()

    def get_pos_config_by_user(self):
        emp = self.env['hr.employee'].search([('user_id', '=', self.env.uid), ('company_id', '=', self.env.company.id)], limit=1)
        pos_config_id = None
        if emp:
            for pos_config in self.env['pos.config'].search([('company_id', '=', self.env.company.id)]):
                if emp.id in pos_config.employee_ids.ids:
                    pos_config_id = pos_config.id
                    break
        return pos_config_id

    def send_to_pos(self):
        if self.x_sent_to_pos:
           raise ValidationError('Este presupuesto ya había sido enviado a caja')

        # if self._get_forbidden_state_confirm() & set(self.mapped('state')):
        #     raise ValidationError(_('It is not allowed to confirm an order in the following states: %s') % (', '.join(self._get_forbidden_state_confirm())))

        if not self.x_document_type:
            raise ValidationError('Debe seleccionar el tipo de comprobante que necesita el cliente')

        # pos_config = self.env['pos.config'].search([('company_id','=', self.company_id.id),('active','=',True)], limit=1)
        # if not pos_config:
        #    raise ValidationError('No existe un punto de venta definido en la compañía: %s' % (self.company_id.name))

        if not self.x_pos_config_id:
            raise ValidationError('No han seleccionado la caja punto de venta destino')

        opened_session = self.env['pos.session'].search([('config_id', '=', self.x_pos_config_id.id), ('state', '=', 'opened')], order='id desc')

        if not opened_session:
            raise ValidationError('No existe ninguna sesión de Punto de Venta abierta, en el punto de venta: %s ' % (pos_config.name))

        data_vals = {
            'name': '/',
            'session_id': opened_session[0].id,
            'user_id': self.user_id.id,
            'company_id': self.company_id.id,
            'date_order': datetime.date.today(),
            'state': 'draft',
            'partner_id': self.partner_id.id,
            'fiscal_position_id': self.partner_id.property_account_position_id.id,
            'x_name_to_print': self.partner_id.name,
            'x_document_type': self.x_document_type,
            'amount_tax': self.amount_tax,
            'amount_total': self.amount_total,
            'amount_paid': 0.0,
            'amount_return': 0.0,
            'pricelist_id': self.pricelist_id.id,
            'currency_rate': self.currency_rate,
            'crm_team_id': self.team_id.id,
            'note': self.note,
            'employee_id': self.x_employee_id.id,
            'x_sale_order_id': self.id
        }

        # pos_order = self.create_pos_order(data_vals)
        # crea el movimmiento en pos_order
        pos_order = self.env['pos.order'].create(data_vals)
        pos_order_id = pos_order.id
        for line in self.order_line:
            line_vals = {
                'order_id': pos_order_id,
                'full_product_name': line.name,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
                'price_subtotal_incl': line.price_total,
                'discount': line.discount,
                'company_id': line.company_id.id,
                'product_id': line.product_id.id,
                'qty': line.product_uom_qty,
                'tax_ids': line.tax_id
            }
            res = self.env['pos.order.line'].create(line_vals)

        self.x_pos_order_id = pos_order_id
        self.write({'state': 'sale', 'date_order': fields.Datetime.now(), 'x_sent_to_pos': True, 'x_date_sent_pos': fields.Datetime.now() })
        self.message_post(body='Enviado a Cajas (id: %s)' % (str(pos_order_id)))
        # return pos_order
