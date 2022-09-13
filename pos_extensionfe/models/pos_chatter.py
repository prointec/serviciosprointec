from odoo import api, fields, models, _

class pos(models.Model):
    _name = 'pos.order'
    _inherit = ['pos.order', 'mail.thread']
