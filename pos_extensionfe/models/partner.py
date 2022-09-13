# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

from odoo.exceptions import Warning, UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountFiscalPositionInherit(models.Model):
    _inherit = 'account.fiscal.position'


    @api.model
    def create(self, vals):
        res = super(AccountFiscalPositionInherit, self).create(vals)
        if res.company_id:
            for pos in  self.env['pos.config'].search([('company_id','=',res.company_id.id)]):
                pos.write( {'fiscal_position_ids': [(4, res.id)] } )
        return res
