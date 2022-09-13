# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime


class AccountPaymeny(models.Model):
    _inherit = "account.payment"

    x_destination_journal_id = fields.Many2one('account.journal', string='Transferir a',
                                               domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]", readonly=True,
                                               states={'draft': [('readonly', False)]})
    x_transfer_move = fields.Many2one(
        comodel_name='account.payment',
        string='Entrada de la transferencia', readonly=True, ondelete='cascade',
        check_company=True)

    def onchange_payment_type(self):
        if self.is_internal_transfer:
            self.payment_type = 'outbound'

    def action_post(self):
        res = super(AccountPaymeny, self).action_post()
        for payment in self:
            if payment.is_internal_transfer and not payment.x_transfer_move:
                paired_payment = payment.copy(
                    {
                        "journal_id": payment.x_destination_journal_id.id,
                        "x_destination_journal_id": payment.journal_id.id,
                        "payment_type": payment.payment_type == "outbound"
                                        and "inbound"
                                        or "outbound",
                        "move_id": None,
                        "ref": payment.ref,
                        "date":payment.date,
                        "x_transfer_move": payment.id,
                    }
                )
                paired_payment.move_id._post(soft=False)
                payment.x_transfer_move = paired_payment
        return res
