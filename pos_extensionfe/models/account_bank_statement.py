# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError


class AccountBankStmtCashWizardExtend(models.Model):
    _inherit = 'account.bank.statement.cashbox'

    @api.model
    def default_get(self, fields):
        vals = super(AccountBankStmtCashWizardExtend, self).default_get(fields)
        if 'cashbox_lines_ids' not in fields:
            return vals
        config_id = self.env.context.get('default_pos_id')
        if config_id:
            config = self.env['pos.config'].browse(config_id)
            if config.last_session_closing_cashbox.cashbox_lines_ids:
                lines = config.last_session_closing_cashbox.cashbox_lines_ids
            else:
                lines = config.default_cashbox_id.cashbox_lines_ids
            if self.env.context.get('balance', False) == 'start':
                vals['cashbox_lines_ids'] = [[0, 0, {'coin_value': line.coin_value, 'x_currency_id': line.x_currency_id, 'number': line.number, 'subtotal': line.subtotal}]
                                             for line in lines]
            else:
                vals['cashbox_lines_ids'] = [[0, 0, {'coin_value': line.coin_value, 'x_currency_id': line.x_currency_id, 'number': 0, 'subtotal': 0.0}]
                                             for line in lines]
        return vals


class AccountCashboxLineExtend(models.Model):
    _inherit = 'account.cashbox.line'
    _order = 'x_currency_id asc, coin_value'

    x_currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id,
                                    string='Tipo de Moneda',domain="[('active', '=', True)]")
    x_exchange_rate = fields.Float(string='Tipo de Cambio', store=True)
    x_payment_amount = fields.Float(string='Monto pagado', compute='_sub_total')


    @api.onchange('x_currency_id')
    def _onchage_x_currency_id(self):
        session_id = self.env.context.get("pos_session_id")
        if not session_id:
            raise ValidationError('No fue posible obtener el número de sesión')

        if self.x_currency_id.id == self.env.company.currency_id.id:
            exchange_rate = 1
        else:
            payment_rate = self.env['pos.payment'].search([('session_id', '=', int(session_id)), ('x_currency_id', '=', self.x_currency_id.id)],
                                                           limit=1, order='id desc')
            if not payment_rate:
                exchange_rate = self.env['res.currency'].search([('id', '=', self.x_currency_id.id)]).x_exchange_rate
            else:
                exchange_rate = payment_rate.x_exchange_rate
        for line in self:
            line.x_exchange_rate = exchange_rate


    @api.depends('coin_value', 'number', 'x_exchange_rate')
    def _sub_total(self):
        """ Calculates Sub total"""
        for cashbox_line in self:
            if (cashbox_line.x_exchange_rate or 0) == 0:
                cashbox_line._onchage_x_currency_id()
            cashbox_line.x_payment_amount = cashbox_line.coin_value * cashbox_line.number
            cashbox_line.subtotal = (cashbox_line.coin_value * cashbox_line.number) * cashbox_line.x_exchange_rate
