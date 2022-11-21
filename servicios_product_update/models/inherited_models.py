# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    notification_msg = fields.Char(
        "Mensaje de notificación",
        config_parameter="servicios_product_update.notification_msg",
    )
    notification_time = fields.Float(
        "Tiempo de aparición del mensaje",
        config_parameter="servicios_product_update.notification_time",
    )

    @api.constrains("notification_time")
    def _check_notification_time(self):
        if any(rec.notification_time < 15 for rec in self):
            raise ValidationError(
                "El tiempo no puede ser menor a 15 segundos por motivos de rendimiento"
            )

class ResCompany(models.Model):
    _inherit = "res.company"

    def get_notification_config(self):
        return {
            "msg": self.env["ir.config_parameter"].get_param("servicios_product_update.notification_msg"),
            "time": float(self.env["ir.config_parameter"].get_param("servicios_product_update.notification_time")),
        }
        
class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    can_notify = fields.Boolean()
    notified = fields.Boolean()

class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _prepare_purchase_order(self, company_id, origins, values):
        vals = super()._prepare_purchase_order(company_id, origins, values)
        
        vals.update({
            "can_notify": True,
            "notified": False,
        })

        users = self.env.ref("purchase.group_purchase_user").users

        self.env['mail.message'].create({
            'message_type': "notification",
            'body': "Se ha creado una PO nueva para reabastecer el inventario",
            'subject': "PO desde inventario",
            'partner_ids': [(4, user.partner_id.id) for user in users if users],
            'model': "purchase.order",
            'res_id': self.id,
            'notification_ids': [(0, 0, {
                'res_partner_id': user.partner_id.id,
                'notification_type': 'inbox'
            }) for user in users if users],
            'author_id': self.env.user.partner_id.id or self.env.ref('base.partner_root').id
        })

        return vals

