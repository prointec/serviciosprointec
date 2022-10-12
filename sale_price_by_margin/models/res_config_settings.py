# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    margin_first_pricelist_id = fields.Many2one('product.pricelist', string='Lista de Precio Margen 1',
                                                ondelete="cascade", check_company=True)
    margin_second_pricelist_id = fields.Many2one('product.pricelist', string='Lista de Precio Margen 2',
                                                 ondelete="cascade", check_company=True)
    x_apply_discount_margin = fields.Boolean(string='Incluye Descuento en Margen', default=False,
                                            help='Aplicar el descuento al calcular el precio con los margenes indicados')

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res.update(
            margin_first_pricelist_id=int(self.env['ir.config_parameter'].sudo().get_param('sale_price_by_margin.margin_first_pricelist_id')),
            margin_second_pricelist_id=int(self.env['ir.config_parameter'].sudo().get_param('sale_price_by_margin.margin_second_pricelist_id')),
            x_apply_discount_margin=self.env['ir.config_parameter'].sudo().get_param('sale_price_by_margin.x_apply_discount_margin')
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        param = self.env['ir.config_parameter'].sudo()

        field1 = self.margin_first_pricelist_id and self.margin_first_pricelist_id.id or False
        field2 = self.margin_second_pricelist_id and self.margin_second_pricelist_id.id or False
        field3 = self.x_apply_discount_margin or False

        param.set_param('sale_price_by_margin.margin_first_pricelist_id', field1)
        param.set_param('sale_price_by_margin.margin_second_pricelist_id', field2)
        param.set_param('sale_price_by_margin.x_apply_discount_margin', field3)
