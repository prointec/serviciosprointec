# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class xProductTemplate(models.Model):
    _inherit = "product.template"

    x_margin_first = fields.Float(string='% Margen Precio 1')
    x_margin_second = fields.Float(string='% Margen Precio 2')
    x_round_factor = fields.Float(string='Factor de redondeo', default=5.0)
    x_margin_first_price = fields.Float(string='Precio de Margen 1', compute="_compute_product_price")
    x_margin_second_price = fields.Float(string='Precio de Margen 2', compute="_compute_product_price")
    x_last_cost = fields.Float(string='Último costo', default=1.0, help="Valor de último costo.")
    x_price_update_manual = fields.Boolean(string="Precio actualizado", default=False)

    @api.onchange('x_margin_first', 'x_margin_second', 'x_round_factor')
    def _onchange_x_margin_first(self):
        if self.x_margin_first and self.standard_price:
            x_margin_first_price = self.standard_price * (1 + self.x_margin_first / 100)
            if self.x_round_factor > 0:
                first_amount_i, first_amount_d = divmod(x_margin_first_price, self.x_round_factor)
                if first_amount_d > 0:
                    x_margin_first_price = (first_amount_i * self.x_round_factor) + self.x_round_factor
            self.x_margin_first_price = x_margin_first_price

        if self.x_margin_second and self.standard_price:
            x_margin_second_price = self.standard_price * (1 + self.x_margin_second / 100)
            if self.x_round_factor > 0:
                second_amount_i, second_amount_d = divmod(x_margin_second_price, self.x_round_factor)
                if second_amount_d > 0:
                    x_margin_second_price = (second_amount_i * self.x_round_factor) + self.x_round_factor
            self.x_margin_second_price = x_margin_second_price

    def _compute_product_price(self):
        for product in self:
            if (product.standard_price and product.x_margin_first
                    and product.x_margin_second):
                x_margin_first_price = product.standard_price * (1 + product.x_margin_first / 100)
                x_margin_second_price = product.standard_price * (1 + product.x_margin_second / 100)
                if product.x_round_factor > 0:
                    first_amount_i, first_amount_d = divmod(x_margin_first_price, self.x_round_factor)
                    if first_amount_d > 0:
                        x_margin_first_price = (first_amount_i * self.x_round_factor) + self.x_round_factor
                    second_amount_i, second_amount_d = divmod(x_margin_second_price, self.x_round_factor)
                    if second_amount_d > 0:
                        x_margin_second_price = (second_amount_i * self.x_round_factor) + self.x_round_factor

                product.x_margin_first_price = x_margin_first_price
                product.x_margin_second_price = x_margin_second_price
            else:
                product.x_margin_first_price = 0
                product.x_margin_second_price = 0

    @api.onchange('list_price')
    def _onchange_list_price(self):
        if self.list_price:
            self.x_price_update_manual = True

    def write(self, vals):
        for template in self:
            if 'x_price_update_manual' in vals and vals.get('x_price_update_manual') \
                    and 'list_price' in vals and vals.get('list_price'):
                vals.pop('x_price_update_manual')
                template.message_post(body="El usuario " + self.env.user.name + " ha actualizado el precio de venta: [" + str(template.list_price) + " >> " + str(vals.get('list_price')) + "]")

        return super(xProductTemplate, self).write(vals)