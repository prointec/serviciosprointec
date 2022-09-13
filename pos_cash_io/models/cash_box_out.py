# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import Warning, UserError, ValidationError

import logging
_logger = logging.getLogger(__name__)


class AccountBankStatementLineInherit(models.Model):
    _inherit = 'account.bank.statement.line'

    x_source = fields.Selection(string='Origen',
                                selection=[('cash_io','Cierre de Caja'),
                                            ('express','Vuelto de Express')],
                                help='Indica donde se originó el movimiento', ) 
    x_source_id = fields.Integer(string='Source Id', help='Es el ID de donde proviene el movimiento')


class CashBoxOutInherit(models.TransientModel):
    _inherit = 'cash.box.out'

    x_transaction_type = fields.Selection([('cash_in', 'Ingreso'), ('cash_out', 'Egreso')], string='Transaction Type', required=True)
    x_source = fields.Selection(string='Origen',
                                selection=[('cash_io','Cierre de Caja'),
                                            ('express','Vuelto de Express')],
                                help='Indica donde se originó el movimiento', ) 

    @api.onchange('x_transaction_type', 'amount')
    def onchange_transaction_type(self):
        self.x_source = 'cash_io'
        if self.amount:
            if self.x_transaction_type == 'cash_out':
                self.amount = -abs(self.amount)
            else:
                self.amount = abs(self.amount)

    def _calculate_values_for_statement_line(self, record):
        if not record.journal_id.company_id.transfer_account_id:
            raise UserError(_("You have to define an 'Internal Transfer Account' in your cash register's journal."))
        amount = self.amount or 0.0
        return {
            'date': record.date,
            'statement_id': record.id,
            'journal_id': record.journal_id.id,
            'amount': amount,
            'payment_ref': self.name,
            'x_source': self.x_source,
        }