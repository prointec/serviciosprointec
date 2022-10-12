# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
# from ast import Store

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    x_margin_first_price = fields.Float(string='Precio Márgen 1', compute="_compute_product_price", store=True)
    x_margin_second_price = fields.Float(string='Precio Márgen 2', compute="_compute_product_price", store=True)
    x_old_standard_price = fields.Float(string='Precio pasado', readonly=True, store=True)
    x_margin_first = fields.Float(string='% Margen Precio 1', readonly=True, store=True)
    x_margin_second = fields.Float(string='% Margen Precio 2', readonly=True, store=True)


    @staticmethod
    def _calculate_margin_price(currency_id, margin, price_unit, round_factor):
        if currency_id.name in ('USD', 'EUR'):
            # Dol y Euros no se redondean con el factor
            margin_price = round((price_unit * (1 + margin / 100)), 2)
        else:
            margin_price = round((price_unit * (1 + margin / 100)) / round_factor, 0) * round_factor
        return margin_price

    @api.onchange('price_unit')
    def _onchange_price_unit(self):
        self.ensure_one()
        self.x_old_standard_price = self.product_id.product_tmpl_id.standard_price

    @api.depends('price_unit', 'x_discount', 'x_amount_discount')
    def _compute_product_price(self):
        apply_discount_margin = self.env['ir.config_parameter'].sudo().get_param('sale_price_by_margin.x_apply_discount_margin')
        for line in self:
            line.x_margin_first = 0
            line.x_margin_first_price = 0
            line.x_margin_second = 0
            line.x_margin_second_price = 0
            if line.product_id and line.price_unit:
                product_tmpl = line.product_id.product_tmpl_id
                price_unit = line.x_price_unit  # precio bruto (sin aplicar descuento)
                if apply_discount_margin and line.product_qty != 0 and line.x_amount_discount != 0:
                    price_unit = price_unit - (line.x_amount_discount/ line.product_qty)
                if product_tmpl.x_margin_first:
                    line.x_margin_first = product_tmpl.x_margin_first
                    line.x_margin_first_price = line._calculate_margin_price(line.currency_id, product_tmpl.x_margin_first, price_unit, product_tmpl.x_round_factor)
                if product_tmpl.x_margin_second:
                    line.x_margin_second = product_tmpl.x_margin_second
                    line.x_margin_second_price = line._calculate_margin_price(line.currency_id, product_tmpl.x_margin_second, price_unit, product_tmpl.x_round_factor)

