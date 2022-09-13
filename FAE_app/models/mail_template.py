# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class xMailTemplate(models.Model):
    _inherit = "mail.template"

    # corrige actualizacion de odoo que cambia el owner de los attachment cuando ponent en un template
    def _fix_attachment_ownership(self):
        for record in self:
            for attach in record.attachment_ids.filtered(lambda a: a.res_id == 0):
                attach.write({'res_model': record._name, 'res_id': record.id})
        return self
