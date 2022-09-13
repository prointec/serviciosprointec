# -*- coding: utf-8 -*-
from odoo import fields, models, api, _ 
from datetime import datetime

from odoo.exceptions import Warning, UserError, ValidationError

import logging

_logger = logging.getLogger(__name__)


class POSConfigInherit(models.Model):
    _inherit = 'pos.config'


    # datos para generar el número de documentos
    x_sucursal = fields.Integer(string="Sucursal", copy=True, default="1", 
                                help='Sucursal a la que pertence la Caja')
    x_terminal = fields.Integer(string="Terminal", copy=False,
                                help='Número de Caja o Terminal de Punto de Venta')
    # consecutivos de documentos
    x_sequence_FE_id = fields.Many2one("ir.sequence", string="Facturas Electrónicas", copy=False, required=False)
    x_sequence_TE_id = fields.Many2one("ir.sequence", string="Tiquetes Electrónicos", copy=False, required=False)
    x_sequence_NC_id = fields.Many2one("ir.sequence", string="NC Electrónicas", copy=False, required=False)

    #
    x_deny_payments = fields.Boolean('Deshabilitar Pago POS', copy=False, default=False, 
                    help ='Deshabilita el botón de pago en el Punto de Venta (js)')    
    x_allow_draft_orders = fields.Boolean(string="Permite Ordenes Draft", 
            help='Permite que el POS deje la orden en estado pendiente (Draft) para que sea cobrada en caja' )
    x_copies_ticket = fields.Integer(string="Copias Ticket", copy=False, default=1,
                                help='Cantidad de impresiones del ticket')
    x_product_receipt = fields.Many2one('product.template', string='Cód.Abono Créditos',
                                        help='Código de producto para registrar la línea del documento a abonar')
    x_journal_receipt = fields.Many2one('account.journal', string='Journal Abonos',
                                        help='Journal utilizado para crear el abono en Cuentas por Cobrar')

    @api.onchange('x_terminal')
    def _onchange_xpos_config(self):
        if self.name and not (1 <= self.x_terminal <= 99999):
            raise ValidationError('El número de terminal debe estar entre 1 y 99999')

    # override este método para que muestre la session de cualquier usuario (sesiones de venta)
    def _compute_current_session(self):
        for pos_config in self:
            opened_sessions = pos_config.session_ids.filtered(lambda s: not s.x_employee_id and s.state not in ('closing_control','closed'))
            session = pos_config.session_ids.filtered(lambda s: not s.x_employee_id and s.state not in ('closing_control','closed') and not s.rescue).sorted(lambda r: r.id, reverse=True)
            # cierra todas las sessiones de ventas (las que no tiene cajero asignado) que no tengan ordenes asociadas
            # Conserva la session[0]
            for i in range(1, len(session) ):
                if not session[i].order_ids:
                    session[i].state = 'closed'
                    session[i].stop_at = fields.Datetime.now()
            # sessions ordered by id desc
            pos_config.has_active_session = opened_sessions and True or False           
            if session:
                pos_config.current_session_id = session[0].id
                pos_config.current_session_state = session[0].state
            else:
                pos_config.current_session_id = False
                pos_config.current_session_state = False

    def current_sale_session(self):
        self.ensure_one()
        current_session = self.current_session_id
        if not current_session:
            session = self.session_ids.filtered(lambda s: not s.x_employee_id and not s.state == 'closed' and not s.rescue).sorted(lambda r: r.id, reverse=True)
            if len(session) > 0:
                current_session = session[0]
        return current_session

    def action_select_cashier(self):
        self.ensure_one()
        # self.env.company.currency_id.symbol
        currency_rate_expired = self.env['res.currency'].search([('x_exchange_type', '!=', False), ('x_end_date', '<', fields.Date.today())])
        for rec in currency_rate_expired:
            raise UserError(('El tipo de cambio cambio de la moneda %s está vencido.\n' +
                            'Debe actualizar el tipo de cambio para abrir la caja') % rec.name)
        return {
            'name': 'Seleccionar Cajero',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'xpos.config_cashier',
            'context': {'default_config_id': self.id, 'action_mode_cashier': 'select', },
            'target': 'new',
        }

    def action_close_cashier(self):
        self.ensure_one()
        return {
            'name': 'Cierre de Cajero',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'xpos.config_cashier',
            'context': {'default_config_id': self.id, 'action_mode_cashier': 'close', },
            'target': 'new',
        }