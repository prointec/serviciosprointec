
from odoo import models, fields, api, _
import math
from odoo.exceptions import UserError, ValidationError

import logging

_logger = logging.getLogger(__name__)


class xResCurrency(models.Model):
    _inherit = 'res.currency'

    x_exchange_type = fields.Selection(string='Tipo',
                                       selection=[('manual', 'Manual'), ('calculated', 'Calculado')],
                                       copy=False,
                                       default='manual')
    x_exchange_amount = fields.Float(string='Valor', copy=False,
                                     help='Contiene el monto del tipo de cambio si tipo es manual, de lo contrario aquí se registra '\
                                            'el valor que debe restarse el tipo de cambio oficial de compra')
    x_round_factor = fields.Float(string='Factor Redondeo', copy=False,
                                     help='El redondeo se hace en múltiplos de este factor. Ejemplo, Si el tipo de cambio 684.25\n'\
                                           'con un factor de redondeo de 5, el resultado será 685')
    x_exchange_rate = fields.Float(string='Tipo de Cambio', compute='_compute_x_exchange_rate')
    x_end_date = fields.Date(string='Rige hasta', copy=False)
    x_currency_editable = fields.Boolean(compute='_compute_x_currency_editable', readonly=True)

    def _compute_x_currency_editable(self):
        for rec in self:
            if self.env.user.has_group('point_of_sale.group_pos_manager'):
                rec.x_currency_editable = True
            else:
                rec.x_currency_editable = False

    @api.onchange('x_exchange_type')
    def _onchange_x_exchange_type(self):
        if self.x_exchange_type == 'manual':
            self.x_round_factor = False
        elif self.x_exchange_type == 'calculated':
            if (self.x_round_factor or 0) < 0.05:
                self.x_round_factor = 1
        else:
            self.x_round_factor = False
            self.x_exchange_amount = False
            self.x_end_date = False

    @api.onchange('x_exchange_amount')
    def _onchange_x_exchange_rate(self):
        if self.x_exchange_type == 'manual':
            if (self.x_exchange_amount or 0) <= 0:
                raise ValidationError('El valor debe ser mayor a 0')
            rate = self.get_currency_rate()
            if self.x_exchange_amount > rate.x_cr_rate_buying:
                raise ValidationError('El tipo de cambio no debe ser mayor al tipo de Cambio Compra actual: %s' % (rate.x_cr_rate_buying))
        elif self.x_exchange_type == 'calculated':
            # calculado
            if (self.x_exchange_amount or 0) > 0:
                raise ValidationError('El valor no puede ser mayor a 0, debe ser 0 menor  para comprar la divisa a un valor conveniente para la empresa')

    @api.onchange('x_round_factor')
    def _onchange_x_round_factor(self):
        if self.x_exchange_type == 'calculated':
            round_factor = abs(self.x_round_factor or 1)
            if round_factor == 0:
                round_factor = 1
            self.x_round_factor = round_factor
        else:
            self.x_round_factor = False

    @api.onchange('x_end_date')
    def _onchange_x_end_date(self):
        if self.x_exchange_type and self.x_end_date < fields.Date.today():
            raise ValidationError('La fecha de de vencimiento del tipo de cambio, no debe ser inferior a la fecha de hoy')

    @api.depends('x_exchange_type', 'x_round_factor', 'x_exchange_amount')
    def _compute_x_exchange_rate(self):
        for rec in self:
            tipo_cambio = None
            if rec.x_exchange_type == 'manual':
                tipo_cambio = rec.x_exchange_amount
            elif rec.x_exchange_type == 'calculated':
                rate = rec.get_currency_rate()
                if rate and rate.x_cr_rate_buying:
                    tipo_cambio = math.floor((rate.x_cr_rate_buying + (rec.x_exchange_amount or 0)) / rec.x_round_factor) * rec.x_round_factor
            rec.x_exchange_rate = tipo_cambio

    @api.model
    def get_currency_rate(self):
        rate = self.env['res.currency.rate'].search(['&', ('currency_id', '=', self._origin.id),
                                                     '|', ('company_id', '=', self.env.company.id), ('company_id', '=', False)],
                                                    order="name desc", limit=1)
        return rate
