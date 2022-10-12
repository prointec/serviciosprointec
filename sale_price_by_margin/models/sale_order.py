from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
# import base64
# from bs4 import BeautifulSoup
import logging
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def create(self, vals):
        for line in vals['order_line']:
            product = self.env['product.product'].search([('id', '=', line[2]['product_id'])]).product_tmpl_id
            price = line[2]['price_unit'] - ((line[2]['discount'] * line[2]['price_unit']) / 100)
            price_list = self.env['product.pricelist'].search([('id', '=', vals['pricelist_id'])])
            final_price = price / price_list.currency_id.rate
            if int(product.standard_price) >= int(final_price) and product.name:
                raise UserError(
                    'El precio de venta es igual o inferior al costo del producto, porfavor revisar el precio de venta del producto ' + product.name)
        return super(SaleOrder, self).create(vals)
