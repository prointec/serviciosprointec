# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, tools, _


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x_list_price_IVA = fields.Float(string="Precio de venta con impuestos", compute='_compute_list_price_IVA',
                                    store=False)

    @api.onchange('list_price', 'taxes_id')
    def _compute_list_price_IVA(self):
        for product in self:
            if product.list_price and product.taxes_id:
                taxes_amount = 0
                for tax in product.taxes_id:
                    taxes_amount += (product.list_price * tax.amount)/100
                product.x_list_price_IVA = product.list_price + taxes_amount
            else:
                product.x_list_price_IVA = product.list_price or 0