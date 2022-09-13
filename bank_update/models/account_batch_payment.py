# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountBatchPayment(models.Model):
    _inherit = "account.batch.payment"

    journal_id = fields.Many2one('account.journal', string='Bank', domain=[('type', 'in', ('bank', 'cash'))], required=True, readonly=True,
                                 states={'draft': [('readonly', False)]})
