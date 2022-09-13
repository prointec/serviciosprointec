# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.tools import float_is_zero, float_round, float_compare

from odoo.exceptions import Warning, UserError, ValidationError

class PosSetExpress(models.TransientModel):
    _name = 'pos.set.express'
    _description = 'Point of Sale Set Express Service'

    order_id = fields.Integer(string='Order id')
    amount_total = fields.Float(string='Total Factura')
    amount_pays_with = fields.Float(string='Paga con', required=True)
    amount_return_prev = fields.Float(string='Vuelto ya Registrado', readonly=True, 
                                    help='Vuelto que ya había sido registrado')
    amount_return = fields.Float(string='Vuelto', required=True)
    amount_return_total = fields.Float(string='Vuelto total', readonly=True, 
                                    help='Suma del Vuelto previamente registrado más el nuevo vuelto')

    @api.model
    def default_get(self, fields_list):
        res = super(PosSetExpress, self).default_get(fields_list)        
        active_id = self.env.context.get('active_id')
        if active_id:
            order = self.env['pos.order'].browse(active_id)        
            res.update( {'order_id': order.id,
                         'amount_total': order.amount_total,
                         'amount_pays_with' : order.x_amount_pays_with,
                         'amount_return_prev' : order.x_amount_return,
                         'amount_return_total' : order.x_amount_return
                         } )
        return res


    @api.onchange('amount_pays_with')
    def onchange_amount_pays_with(self):
        self.ensure_one()
        order = self.env['pos.order'].browse(self.env.context.get('active_id', False))
        if self.amount_pays_with > 0 and self.amount_pays_with < self.amount_total:
            raise Warning('El monto pagado no puede ser menor que el monto del documento')
        elif not self.amount_pays_with:
            self.amount_return = None
        else:
            return_prev = self.amount_return_prev if self.amount_return_prev else 0
            self.amount_return_total = order._get_rounded_amount(self.amount_pays_with - self.amount_total) 
            self.amount_return = self.amount_return_total - return_prev  


    def action_send_express(self):
        self.ensure_one()
        order = self.env['pos.order'].browse(self.order_id)

        if float_round((self.amount_return or 0), 0.01) < 0:
            raise Warning('El vuelto a entregar es Menor a 0')

        order.x_amount_pays_with = order._get_rounded_amount(self.amount_pays_with)
        order.x_amount_return_total = order._get_rounded_amount(self.amount_return_total)
        order.action_pos_order_express(self.amount_return)

        return {'type': 'ir.actions.act_window_close'}
