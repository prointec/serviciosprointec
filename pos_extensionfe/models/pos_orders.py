# -*- coding: utf-8 -*-

from odoo import fields, models, api, _ 
from odoo.tools import float_is_zero, float_compare, float_round, DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from xml.sax.saxutils import escape
from lxml import etree
import datetime
import time
import base64
import pytz
import json


import odoo.addons.FAE_app.models.fae_utiles as fae_utiles
import odoo.addons.FAE_app.models.fae_enums as fae_enums

from odoo.exceptions import Warning, RedirectWarning, UserError, ValidationError

import logging

_logger = logging.getLogger(__name__)


class posInvoiceInherit(models.Model):
    _inherit = "account.move"

    x_pos_order_id = fields.Integer(string="POS Order Id", compute="_compute_pos_order_id")

    def _compute_pos_order_id(self):
        for rec in self:
            if rec.x_electronic_code50:
                pos_order = self.env['pos.order'].search([('x_move_id','=',self.id)], limit=1)
                rec.x_pos_order_id = pos_order.id if pos_order else None


class PosOrderLineInherit(models.Model):
    _inherit = "pos.order.line"

    tax_ids = fields.Many2many('account.tax', string='Taxes', readonly=False)
    x_tax_ids_for_calc_amount = fields.Boolean(default=False, copy=True,
                                               help='Indica que los tax_ids registrados en la tabla son lo que se usan para el cálculo de impuesto')
    x_parent_state = fields.Selection(related='order_id.state', store=False, readonly=True)
    x_product_code = fields.Char(related='product_id.default_code', store=False, readonly=True)

    x_discount_note = fields.Char(string="Motivo descuento", copy=True, size=80, required=False, )
    x_other_charge_partner_id = fields.Many2one("res.partner", copy=True, string="Tercero otros cargos",)

    x_move_receipt = fields.Many2one("account.move", copy=True, string="Factura",)
    x_amount_total_line = fields.Float(string="Monto Total", readonly=True)
    x_last_balance = fields.Float(string="Monto Anterior", help='Saldo por Cobrar antes de este pago',)


    # override el onchange original de odoo, para poder permitir cambiar los impuestos
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id.id:
            return
        if not self.order_id.pricelist_id:
            raise UserError(
                _('You have to select a pricelist in the sale form !\n'
                  'Please set one before choosing a product.'))
        if self.product_id.type != 'service' and not self.product_id.x_cabys_code_id:
            raise UserError('El artículo: %s no tiene código CAByS' % (self.product_id.default_code or self.product_id.name) )

        self.x_tax_ids_for_calc_amount = True
        tax_ids = self.product_id.taxes_id.filtered(lambda r: not self.company_id or r.company_id == self.company_id)

        price = self.order_id.pricelist_id.get_product_price(self.product_id, self.qty or 1.0, self.order_id.partner_id)
        self._onchange_qty()
        tax_ids_after_fiscal_position = self.order_id.fiscal_position_id.map_tax(tax_ids, self.product_id, self.order_id.partner_id)
        self.tax_ids = tax_ids_after_fiscal_position
        self.tax_ids_after_fiscal_position = tax_ids_after_fiscal_position
        self.price_unit = self.env['account.tax']._fix_tax_included_price_company(price, self.product_id.taxes_id, tax_ids_after_fiscal_position, self.company_id)

    # override el onchange original de odoo, para poder permitir cambiar los impuestos
    # @api.model
    @api.onchange('qty', 'discount', 'price_unit', 'tax_ids')
    def _onchange_qty(self):
        res = self._compute_amount_line_all()
        self.price_subtotal = res['price_subtotal']
        self.price_subtotal_incl = res['price_subtotal_incl']

    @api.onchange('qty')
    def _onchange_pos_line_qty(self):
        if self.order_id.x_move_type == 'refund' and self.qty > 0:
            self.qty = -abs(self.qty)

    @api.onchange('tax_ids')
    def _change_xpos_line_tax_ids(self):
        for line in self:
            line.x_tax_ids_for_calc_amount = True
            if line.product_id:
                line._get_tax_ids_after_fiscal_position()
            res = line._compute_amount_line_all()
            line.update(res)
        self.order_id.calc_amount_total()

    @api.model
    def _get_tax_ids_after_fiscal_position(self):
        for line in self:
            line.tax_ids_after_fiscal_position = line.tax_ids if line.x_tax_ids_for_calc_amount else \
                                                line.order_id.fiscal_position_id.map_tax(line.tax_ids, line.product_id, line.order_id.partner_id)

    @api.model
    def _compute_amount_line_all(self):
        self.ensure_one()
        if not self.currency_id:
            currency = self.env.company.currency_id
        else:
            currency = self.currency_id

        price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        taxes = self.tax_ids.compute_all(price, self.order_id.pricelist_id.currency_id, self.qty, product=self.product_id, partner=self.order_id.partner_id)
        res = {
            'price_subtotal_incl': currency.round(taxes['total_included']),
            'price_subtotal': currency.round(taxes['total_excluded']),
            }
        return res


class PosOrderInherit(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _default_xpos_currency(self):
        return self.company_id.currency_id.id

    # def _default_session_id(self):
    #     return self.env.context.get("cashier_session_id", 0)

    # redefine campos existentes
    company_id = fields.Many2one(default=lambda self: self.env.company)
    session_id = fields.Many2one(readonly=False, default=lambda self: self.env.context.get("cashier_session_id", 0))
    amount_return = fields.Float(default=0, copy=False,)
    amount_paid = fields.Float(default=0, copy=False)
    payment_ids = fields.One2many(copy=False)

    # Otros campos
    employee_id = fields.Many2one('hr.employee', string='Vendedor', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', store=True,                                 
                                    default=_default_xpos_currency,
                                    help='* currency company' ,
                                    )
    x_move_type = fields.Selection(string="Tipo doc",
                                    selection=[('invoice', 'Factura'),
                                            ('refund', 'Devolución'), 
                                            ('receipt', 'Abono Crédito')],
                                    copy=False, default='invoice', 
                                    )
    x_name_to_print = fields.Char(string='Nombre Factura', copy=False, readonly=True)
    x_customer_name = fields.Char(string='Nombre Cliente', compute='_compute_customer_name', search="_search_customer_name")
    x_is_partial = fields.Boolean('Pago Parcial', copy=False)
    x_is_express = fields.Boolean('Para Entrega', copy=False)
    x_amount_untaxed = fields.Float(string='Untaxed Amount', readonly=True, compute='_compute_amount_untaxed') 
    x_amount_due = fields.Float("Amount Due",compute="get_amount_due", copy=False)
    x_amount_return_total = fields.Float("Vuelto Express", copy=False)
    x_amount_return = fields.Float("Saldo Vuelto Express", copy=False)
    x_amount_pays_with = fields.Float(string='Paga Express con', copy=False, states={'draft': [('readonly', False)]}, readonly=True, digits=0)
    x_cashier_session_id = fields.Integer(string='session id', compute='_compute_cashier_session_id' )

    # campos FAE    
    x_document_type = fields.Selection(string="Tipo Comprobante",
                                        selection=[('FE', 'Factura Electrónica'),
                                                ('TE', 'Tiquete Electrónico'),
                                                ('NC', 'Nota de Crédito'), ],
                                        required=False, default='TE', 
                                        )
    x_sequence = fields.Char(string="Núm.Consecutivo", required=False, readonly=True, copy=False, index=True)
    x_electronic_code50 = fields.Char(string="Clave Numérica", required=False, copy=False, index=True)
    x_issue_date = fields.Char(string="Fecha Emisión", size=(30), required=False, copy=False)
    x_currency_rate = fields.Float(string="Tipo Cambio", required=False, copy=False)
    x_state_dgt = fields.Selection(string="Estado DGT",
                                    copy=False,
                                    selection=[('PRO', 'Procesando'),
                                               ('1', 'Aceptado'),
                                               ('2', 'Rechazado'),
                                               ('FI', 'Firma Inválida'),
                                               ('ERR', 'Error'),
                                               ('ENV', 'Reenviar')])
    x_reference_code_id = fields.Many2one("xreference.code", string="Cod.Motivo referencia", required=False, copy=False, )
    x_invoice_reference_id = fields.Many2one("pos.order", string="Doc.Referencia", required=False, copy=False)
    x_reference_document_type_id = fields.Many2one("xreference.document", string="Tipo Doc.Referencia", required=False, )
    x_reference_sequence = fields.Char(related="x_invoice_reference_id.x_sequence", store=False, readonly=True)

    x_xml_comprobante = fields.Binary(string="XML documento", required=False, copy=False, attachment=True )
    x_xml_comprobante_fname = fields.Char(string="Nombre archivo Comprobante XML", required=False, copy=False )
    x_xml_respuesta = fields.Binary(string="XML Respuesta", required=False, copy=False, attachment=True )
    x_xml_respuesta_fname = fields.Char(string="Nombre archivo Respuesta DGT", required=False, copy=False )
    x_response_date = fields.Datetime(string="Fecha Respuesta", required=False, copy=False)
    x_mensaje_respuesta = fields.Char(string="Mensaje Respuesta")

    x_error_count = fields.Integer(string="Cant Errores DGT", copy=False, required=False, default=0 )

    x_state_email = fields.Selection(string="Estado Email",
                                     selection=[('SC', 'Sin cuenta de correo'),
                                                ('E', 'Enviado'),
                                                ('NOE', 'No Envia')],
                                     copy=False)
    x_show_generate_xml_button = fields.Boolean(compute='_compute_x_show_generate_xml_button')

    x_move_id = fields.Many2one("account.move", string="Invoice", copy=False)
    x_sale_order_id = fields.Many2one("sale.order", string="Cotización", copy=False)
    x_rejection_processed  = fields.Boolean(string="Rechazo DGT Reprocesado", default=False, copy=False,
                                            help="Indica si el Documento rechazado fue reprocesado")
    x_pend_recalc = fields.Boolean(string='Pending Recalculation', copy=False, default=True)

    _sql_constraints = [('post_order_x_electronic_code50_uniq', 'unique (company_id, x_electronic_code50)',
                        "La clave numérica deben ser única"),
                        ]

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(PosOrderInherit, self).fields_view_get(view_id=view_id,
                                                            view_type=view_type,
                                                            toolbar=toolbar,
                                                            submenu=submenu)
        doc = etree.XML(res['arch'])
        if view_type in ('tree', 'form') and self.env.context.get("cashier_session_id", 0) > 0:
            doc.set('create', '1')

        res['arch'] = etree.tostring(doc)
        return res

    # override la función original de odoo, para poder permitir cambiar los impuestos
    @api.model
    def _amount_line_tax(self, line, fiscal_position_id):
        taxes = line.tax_ids
        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
        taxes = taxes.compute_all(price, line.order_id.pricelist_id.currency_id, line.qty, product=line.product_id, partner=line.order_id.partner_id or False)['taxes']
        return sum(tax.get('amount', 0.0) for tax in taxes)

    @api.onchange('partner_id')
    def _onchange_xpos_partner_id(self):
        for rec in self:
            if rec.partner_id:
                rec.x_name_to_print = rec.partner_id.name
            if rec.x_move_type == 'refund':
                rec.x_document_type = 'NC' if not rec.x_invoice_reference_id or rec.x_invoice_reference_id.x_state_dgt in ('2', 'FI') else None
            elif rec.partner_id and rec.partner_id.x_identification_type_id and rec.partner_id.vat:
                rec.x_document_type = 'FE'
            else:
                rec.x_document_type = 'TE'

            if rec.partner_id:
                rec.x_name_to_print = rec.partner_id.name

            rec.fiscal_position_id = None if not rec.partner_id else rec.partner_id.property_account_position_id
            if rec.lines:
                rec._onchange_fiscal_position_id()
                rec.calc_amount_line_all()
        return super(PosOrderInherit, self)._onchange_partner_id()

    @api.onchange('fiscal_position_id')
    def _onchange_fiscal_position_id(self):
        for line in self.lines:
            tax_ids = line.product_id.taxes_id.filtered(lambda r: not self.company_id or r.company_id == self.company_id)
            line.tax_ids = self.fiscal_position_id.map_tax(tax_ids, line.product_id, self.partner_id)
            line.tax_ids_after_fiscal_position = line.tax_ids


    @api.onchange('payment_ids', 'lines')
    def _onchange_amount_all(self):
        for order in self:
            currency = order.pricelist_id.currency_id
            if not currency:
                order.pricelist_id = self.env['product.pricelist'].search([('company_id', 'in', (False, self.env.company.id)),
                                                      ('currency_id', '=', self.env.company.currency_id.id)], limit=1)
                currency = order.pricelist_id.currency_id
            order.amount_paid = sum(payment.amount for payment in order.payment_ids)
            order.amount_return = sum(payment.amount < 0 and payment.amount or 0 for payment in order.payment_ids)
            order.amount_tax = currency.round(sum(self._amount_line_tax(line, order.fiscal_position_id) for line in order.lines))
            amount_untaxed = currency.round(sum(line.price_subtotal for line in order.lines))
            order.amount_total = order.amount_tax + amount_untaxed

    @api.depends('state')
    def _compute_cashier_session_id(self):
        self.x_cashier_session_id = self.env.context.get("cashier_session_id", 0)

    # Crea una copia de la orden con el signo que se indique en el parámetro
    def copia_orden(self, session_id, type, fill_reference=True, is_reversion=False):
        name_suffix = ""
        if type == 'cred':
            # hacer un reembolso (NC si no el documento fuente no fue rechazado)            
            signo = -1
            new_move_type = 'refund'
            document_type_dest = 'NC' if self.x_document_type else None
            name_suffix = _(' REFUND')
        else:
            # Hacer una Factura, Tiquete o ND
            signo = 1
            new_move_type = 'invoice'
            document_type_dest = 'ND' if self.x_document_type == 'NC' else self.x_document_type
        
        if self.x_state_dgt in ('2', 'FI') and is_reversion:
            # si es una reversión de un documento rechazado, entonces la revesión no la hace electrónica
            document_type_dest = None

        vals = {'name': self.name + name_suffix,
                'session_id': session_id,
                'date_order': fields.Datetime.now(),
                'pos_reference': self.pos_reference,
                'lines': [],
                'amount_tax': abs(self.amount_tax) * signo,
                'amount_total': abs(self.amount_total) * signo,
                'amount_paid': 0,
                'state':'draft',
                'x_move_type': new_move_type,
                'employee_id': self.employee_id.id,
                'x_name_to_print' : self.x_name_to_print,
                'x_document_type': document_type_dest,
                'x_pend_recalc': False,
            }
        new_order = self.copy( vals )

        if fill_reference:
            rec_reference_code = self.env['xreference.code'].search([('code', '=', '01')], limit=1)         
            if new_move_type == self.x_move_type and self.x_state_dgt == '2':
                # Es del mismo tipo y el fuente fue rechazado
                ref_docum_code = '10'   # =Sustituye factura rechazada por el Ministerio de Hacienda
            else:
                ref_docum_code = fae_enums.tipo_doc_num.get(self.x_document_type)
            rec_reference_document_type = self.env['xreference.document'].search([('code','=',ref_docum_code)], limit=1)                
            new_order.x_reference_code_id = rec_reference_code.id
            new_order.x_invoice_reference_id = self.id
            new_order.x_reference_document_type_id = rec_reference_document_type.id

        # copia las líneas
        for line in self.lines:
            PosOrderLineLot = self.env['pos.pack.operation.lot']
            for pack_lot in line.pack_lot_ids:
                PosOrderLineLot += pack_lot.copy()
            line_vals = { 'name': line.name + name_suffix,
                          'qty': abs(line.qty) * signo,
                          'order_id': new_order.id,
                          'price_subtotal': abs(line.price_subtotal) * signo,
                          'price_subtotal_incl': abs(line.price_subtotal_incl) * signo,
                          'pack_lot_ids': PosOrderLineLot,
                        }
            line.copy( line_vals )
        
        return new_order

    def refund(self):
        self.ensure_one()
        if not self.x_cashier_session_id:
            raise UserError("Debe seleccionar un Cajero para realizar una devolución")
        if self.x_move_type == 'refund':
            raise UserError("No se puede realizar una Devolución sobre una devolución")

        current_session = self.current_cashier_session()

        new_order = self.copia_orden(current_session.id, type='cred', fill_reference=True, is_reversion=True)

        return {
            'name': _('Return Products'),
            'view_mode': 'form',
            'res_model': 'pos.order',
            'res_id': new_order.id,
            'view_id': False,
            'context': self.env.context,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    # Para un documento rechazado, se crear un documento de reversión y el que lo sustituye
    def action_recrea_documento(self):
        self.ensure_one()
        if self.state == 'draft' or self.x_state_dgt not in ('1','2'):
            raise ValidationError('El documento está en estado Borrador o no ha sido generado a hacienda ')
            return
        if self.x_rejection_processed:
            raise ValidationError('El documento ya había sido reprocesado')
        # if self.to_invoice:
        #     raise ValidationError('El documento fue pasado a crédito por lo que debe reprocesarse en ese módulo')

        sale_session = self.session_id.config_id.current_sale_session()

        if not sale_session:
            # si no encuentra una session de ventas de POS, entonces usa la session de cajero activo
            sale_session = self.current_cashier_session()

        if not sale_session:
            raise ValidationError('No se pudo localizar una session de ventas abierta')

        if self.x_move_type == 'invoice':
            # es un Cargo (Factura, Tiquete o ND), entonces crea un reembolso y nuevamente el cargo
            new_order_rev  = self.copia_orden(sale_session.id, type='cred', fill_reference=True, is_reversion=True)
            new_order_same = self.copia_orden(sale_session.id, type='deb', fill_reference=True)
        else:
            # El fuente es un crédito, entonces crea el Débito y nuevamente el reembolso
            new_order_rev  = self.copia_orden(sale_session.id, type='deb', fill_reference=True, is_reversion=True)
            new_order_same = self.copia_orden(sale_session.id, type='cred', fill_reference=True)

        self.x_rejection_processed = True
        # los documentos creado tiene el x_invoice_reference_id que apunta a este documento rechazado        

        # return { 'warning': {'title': 'Warning!', 'message': 'The warning text'}}
        return {
            'name': _('Return Products'),
            'view_mode': 'form',
            'res_model': 'pos.order',
            'res_id': new_order_rev.id,
            'view_id': False,
            'context': self.env.context,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    @api.onchange('x_document_type')
    def _onchange_document_type(self):
        if not self.x_document_type or self.x_move_type == 'receipt':
            self.x_document_type = None
            return
        elif not self.x_move_type:
            self.x_move_type = 'refund' if self.amount_total < 0 else 'invoice'

        if self.x_move_type == 'refund' and self.x_document_type != 'NC':
            self.x_document_type = 'NC'
        elif self.x_move_type == 'invoice' and self.x_document_type == 'NC':
            self.x_document_type = 'TE'

    @api.onchange('session_id')
    def _onchange_session_id(self):
        if self.session_id:
            self.company_id = self.session_id.company_id.id

    @api.model
    def _order_fields(self, ui_order):
        res = super(PosOrderInherit, self)._order_fields(ui_order)
        if not res.get('employee_id'):
            res['employee_id'] = res.get('user_id')
        if 'x_is_partial' in ui_order:
            res['x_is_partial'] = ui_order['x_is_partial']
            res['x_name_to_print'] = ui_order['x_name_to_print']
            res['note'] = ui_order['note']
            res['x_document_type'] = ui_order['x_document_type']
        if 'x_amount_due' in ui_order:
            res['x_amount_due'] = ui_order['x_amount_due']
        return res

    @api.depends('state', 'x_sequence')
    def _compute_x_show_generate_xml_button(self):
        for inv in self:
            if inv.state == 'draft':
                inv.x_show_generate_xml_button = False
            elif (inv.state in ('paid','posted','invoiced')
                    and ((inv.x_document_type in ('FE','TE','NC') and not inv.x_sequence)
                        or (inv.x_state_dgt == '1' and not inv.x_xml_comprobante)
                        or inv.x_state_dgt == 'ENV'
                        or (inv.x_state_dgt == 'ERR' and inv.x_error_count >= 10))):
                inv.x_show_generate_xml_button = True
            elif not inv.x_state_dgt or not inv.x_xml_comprobante:
                inv.x_show_generate_xml_button = True
            else:
                inv.x_show_generate_xml_button = False

    @api.depends('amount_total')
    def _compute_amount_untaxed(self):
        for rec in self:
            rec.x_amount_untaxed = rec.amount_total - rec.amount_tax

    def _search_customer_name(self, operator, value):
        result = self.search([]).filtered(lambda r : False if not r.x_customer_name else r.x_customer_name.lower().find(value) >= 0 )
        return [('id', '=', [x.id for x in result] if result else False )]

    @api.depends('partner_id', 'x_customer_name')
    def _compute_customer_name(self):
        for rec in self:
            if rec.partner_id:
                rec.x_customer_name = rec.partner_id.name
            else:
                rec.x_customer_name = rec.x_name_to_print

    def current_cashier_session(self):
        return self.env['pos.session'].search([('id', '=', self.x_cashier_session_id)], limit=1)

    def calc_amount_total(self):
        for order in self:
            currency = order.pricelist_id.currency_id
            order.amount_tax = currency.round(sum(self._amount_line_tax(line, order.fiscal_position_id) for line in order.lines))
            amount_untaxed = currency.round(sum(line.price_subtotal for line in order.lines))
            order.amount_total = order.amount_tax + amount_untaxed

    def calc_amount_line_all(self):
        cant_lineas = 0
        if self.lines and self.state == 'draft':
            amount_total = amount_tax = 0
            for line in self.lines:
                cant_lineas += 1
                res = line._compute_amount_line_all()
                line.price_subtotal = res['price_subtotal']
                line.price_subtotal_incl = res['price_subtotal_incl']
                amount_total += line.price_subtotal_incl
                amount_tax += (line.price_subtotal_incl - (line.price_subtotal if line.price_subtotal != None else 0))
            self.amount_total = amount_total
            self.amount_tax = amount_tax
            self._compute_amount_untaxed()

    def _message_post(self, subject, body):
        self.message_post(body= body, subject= subject )
        _logger.info('>> pos_extensionfe._message_post: order %s msg: %s', self.name, body)

    def action_pos_order_express(self, cash_box_amount_return):
        self.x_is_express = True
        self.x_amount_return = self.x_amount_return_total
        if cash_box_amount_return and cash_box_amount_return != 0:
            current_session = self.current_cashier_session()
            cash_statement = current_session.cash_register_id
            if cash_statement.state == 'confirm':
                raise UserError(_("You cannot put/take money in/out for a bank statement which is closed."))
            if self.name == '/':
                self.name = self.config_id.sequence_id._next()
            payment_ref = 'Vuelto ' + (self.pos_reference if self.pos_reference else self.name)
            values = {
                'date': cash_statement.date,
                'statement_id': cash_statement.id,
                'journal_id': cash_statement.journal_id.id,
                'amount': -cash_box_amount_return, 
                'payment_ref': payment_ref,
                'x_source' : 'express',
                'x_source_id' : self.id,
                'ref': current_session.name + ' - ' + self.name,
            }
            account = cash_statement.journal_id.company_id.transfer_account_id
            self.env['account.bank.statement.line'].with_context(counterpart_account_id=account.id).create(values)
        return {}
    
    def get_amount_due(self):
        for order in self :
            if order.amount_paid - order.amount_total > 0:
                order.x_amount_due = 0
            else:
                order.x_amount_due = order.amount_total - order.amount_paid

    @api.model
    def create(self, vals):
        date_order = vals.get('date_order')
        if date_order and fields.Date.from_string(date_order) < datetime.datetime.now().date():
            vals.update({'date_order': datetime.datetime.now()})
        res = super(PosOrderInherit, self).create(vals)
        if res.partner_id and not res.x_name_to_print:
            res.x_name_to_print = res.partner_id.name
        if res.x_move_type in ('invoice','refund'):
            if not res.x_document_type and res.x_move_type == 'refund':
                res.x_document_type = 'NC'
            elif not res.x_document_type:
                res.x_document_type = 'FE' if res.partner_id else 'TE'
        pend_recalc = False
        for line in res.lines:
            if not line.x_tax_ids_for_calc_amount:
                line.tax_ids = line.tax_ids_after_fiscal_position
                line.x_tax_ids_for_calc_amount = True
                val = line._compute_amount_line_all()
                line.price_subtotal = val['price_subtotal']
                line.price_subtotal_incl = val['price_subtotal_incl']
                pend_recalc = True
        if pend_recalc:
            res.calc_amount_total()
        return res

    def write(self, vals):
        #  raise ValidationError('entro al write, id: ' %str(self.id) )
        res = super(PosOrderInherit, self).write(vals)
        for order in self:
            if order.state != 'draft' or (order.state == 'draft' or order.state == order._origin.state):
                continue    # siguiente registro

            if order.x_move_type != 'receipt':
                if order.x_document_type == 'FE' and order.partner_id and not (order.partner_id.x_identification_type_id and order.partner_id.vat):
                    raise ValidationError('Para Emitir la facturación Electrónica el cliente debe tener definido el tipo de identificáción y el número. ref.: %s  (id %s)'
                                          % (order.name, order.id))

                # currency = order.currency_id
                # _logger.info('>> write:  id: %s   - name: %s   is_partial %s ', order.id, order.name, str(order.x_is_partial))
                # _logger.info('>> write:  vals: %s ', str(vals) )
                if order.name == '/' and order.x_is_partial:
                    order.name = order.config_id.sequence_id._next()
                if order.partner_id and not order.x_name_to_print:
                    order.x_name_to_print = order.partner_id.name

                if order.x_pend_recalc and order.lines:
                    order.x_pend_recalc = False
                    order.calc_amount_line_all()

                if order.company_id.x_fae_mode in ('api-stag', 'api-prod'):
                    # Valida datos para generar el documento Electrónicos
                    # tipo de identificación de la compañía
                    if not order.company_id.x_identification_type_id:
                        raise ValidationError('Debe indicar el tipo de identificación de la compañía')

                    if (order.company_id.x_fae_mode == 'api-stag' and order.company_id.x_test_expire_date <= datetime.date.today() ):
                        raise ValidationError('La llave criptográfica de PRUEBAS está vencida, debe actualizarse con una más reciente')
                    elif (order.company_id.x_fae_mode == 'api-prod' and order.company_id.x_prod_expire_date <= datetime.date.today() ):
                        raise ValidationError('La llave criptográfica está vencida, debe actualizarse con una más reciente')

                    # verifica si existe un tipo de cambio
                    if order.currency_id.name != order.company_id.currency_id.name and (
                            not order.currency_id.rate_ids or not (len(order.currency_id.rate_ids) > 0)):
                        raise ValidationError('No hay tipo de cambio registrado para la moneda: %s' % (order.currency_id.name))

                    if order.x_document_type == 'FE':
                        if not order.partner_id:
                            raise ValidationError('Para emitir una Factura Electrónica se debe indicar el cliente')
                        if order.partner_id.vat and not order.partner_id.x_identification_type_id:
                            raise ValidationError('El cliente debe tener el tipo de identificación al cliente')
                        if order.to_invoice and not order.partner_id.property_payment_term_id:
                            raise ValidationError('Para Venta a crédito el cliente debe tener definido el término de venta (plazo de crédito)')

                    if order.state == 'draft':
                        # Revisa las líneas para verificar que los artículos tiene código CAByS
                        for line in order.lines:
                            if line.product_id and line.product_id.type != 'service' and not (line.product_id.x_cabys_code_id and line.product_id.x_cabys_code_id.code):
                                raise ValidationError('El artículo: %s no tiene código CAByS' % (line.product_id.default_code or line.product_id.name) )

                # revisa los impuestos de las lineas si existen
                if order.amount_tax != 0:
                    err_count = 0
                    for inv_line in order.lines:
                        if (inv_line.price_subtotal != inv_line.price_subtotal_incl) and inv_line.product_id and not inv_line.tax_ids:
                            err_count += 1
                            inv_line.tax_ids = inv_line.product_id.taxes_id.filtered(lambda r: not order.company_id or r.company_id == order.company_id)
                            inv_line._get_tax_ids_after_fiscal_position()
                    if err_count > 0:
                        order._message_post(subject='Error',
                                            body='Se detectaron líneas con impuestos incorrectos, se recalcularon para corregir la inconsistencia' )
                        order.calc_amount_line_all()

            if order.name == '/':
                order.name = order.config_id.sequence_id._next()

        return res

    def genera_consecutivo_dgt(self):
        if not self.x_document_type or self.x_move_type == 'receipt' or self.x_sequence or self.x_electronic_code50:
            return

        sucursal = self.session_id.config_id.x_sucursal
        terminal = self.session_id.config_id.x_terminal
        if terminal < 1:
            raise UserError('El número de terminal debe ser mayor a 0') 
        sequence = None
        if self.x_document_type == 'FE':
            sequence = self.session_id.config_id.x_sequence_FE_id
        elif self.x_document_type == 'TE':
            sequence = self.session_id.config_id.x_sequence_TE_id
        elif self.x_document_type == 'NC':
            sequence = self.session_id.config_id.x_sequence_NC_id
        else:
            raise UserError('No pudo obtener el consecutivo para el tipo documento: %s' % (self.x_document_type) )  

        if not sequence:
            raise UserError('No han definido el consecutivo para el Punto de Venta: %s' % (self.session_id.config_id.name) )

        # Controla que no a haya saltos de consecutivo
        if sequence.number_next_actual >= 5:
            consecutivo = sequence.get_next_char(sequence.number_next_actual - 1)
            prev_x_sequence = fae_utiles.gen_consecutivo(self.x_document_type, consecutivo, sucursal, terminal)
            consecutivo = sequence.get_next_char(max(sequence.number_next_actual, sequence.number_next_actual - 20))
            from_x_sequence = fae_utiles.gen_consecutivo(self.x_document_type, consecutivo, sucursal, terminal)

            sql_cmd = """
                 SELECT x_sequence
                 FROM account_move
                 WHERE x_sequence >= '{from_seq}'
                   AND x_sequence <= '{to_seq}'
                   AND left(x_sequence,10) =  '{pref_seq}'
                   AND x_document_type = '{doc_type}'
                   AND company_id = {company_id}
                 """.format(from_seq=from_x_sequence, to_seq=prev_x_sequence, pref_seq=from_x_sequence[:10]
                            , doc_type=self.x_document_type, company_id=self.company_id.id)
            sql_cmd = sql_cmd + """
                UNION
                SELECT x_sequence
                FROM pos_order
                WHERE x_sequence >= '{from_seq}'
                  AND x_sequence <= '{to_seq}'
                  AND left(x_sequence,10) =  '{pref_seq}'
                  AND x_document_type = '{doc_type}'
                  AND company_id = {company_id}
                """.format(from_seq=from_x_sequence, to_seq=prev_x_sequence, pref_seq=from_x_sequence[:10]
                           , doc_type=self.x_document_type, company_id=self.company_id.id)
            sql_cmd = sql_cmd + """
                ORDER BY 1 DESC
                """
            self._cr.execute(sql_cmd)
            res = self._cr.dictfetchone()
            if res and prev_x_sequence != res.get('x_sequence'):
                raise ValidationError(
                    'Para el tipo de documento: %s se detectó un salto de numeración. No existe el número anterior: %s' % (self.x_document_type, prev_x_sequence))

        if not self.x_issue_date:
            dt_cr = datetime.datetime.today().astimezone(pytz.timezone('America/Costa_Rica'))
            self.x_issue_date = dt_cr.strftime('%Y-%m-%dT%H:%M:%S')

        consecutivo = sequence.next_by_id()

        jdata = fae_utiles.gen_clave_hacienda(self, self.x_document_type, consecutivo, sucursal, terminal)
        self.x_electronic_code50 = jdata.get('clave_hacienda')
        self.x_sequence = jdata.get('consecutivo')

    def _prepare_invoice_vals(self):
        vals = super(PosOrderInherit, self)._prepare_invoice_vals()
        # como no se sabe como pagarán, la disposición de hacienda es que se ponga efectivo
        invoice_date_due = self.date_order + datetime.timedelta(days=1)
        if self.partner_id.property_payment_term_id:
            calc = self.partner_id.property_payment_term_id.compute(self.amount_total, date_ref=self.date_order, currency=self.company_id.currency_id)
            if calc:
                invoice_date_due = fields.Date.from_string( calc[0][0] )
        xpayment_method = self.env['xpayment.method'].search([('code', '=', '01')], limit=1)
        vals.update({'invoice_date_due': invoice_date_due,
                     'x_document_type': self.x_document_type,
                     'x_economic_activity_id' : self.company_id.x_economic_activity_id,
                     'x_sequence': self.x_sequence,
                     'x_electronic_code50' : self.x_electronic_code50,
                     'x_payment_method_id' : xpayment_method.id,
                     'x_issue_date' : self.x_issue_date,
                     'x_state_dgt' : 'POS',    # Pendiente de actualizar por el POS
                     'x_currency_rate' : self.x_currency_rate,
                     'name': self.x_sequence,
                      })
        return vals

    # realiza validaciones 
    def validate_pos_order_data(self):
        if self.x_move_type == 'invoice':
            # son invoice
            doc_type_ref = None if not self.x_invoice_reference_id else self.x_invoice_reference_id.x_document_type
            if self.company_id.x_fae_mode != 'N' and not self.x_document_type and (not doc_type_ref or doc_type_ref != 'NC'):
                raise ValidationError('Debe indicar el tipo de documento electrónico a Generar')
        if self.x_move_type in ('invoice','refund') and self.x_document_type:
            if self.partner_id:
                if self.partner_id.x_special_tax_type == 'E' and not(self.partner_id.x_exo_exoneration_number and self.partner_id.x_exo_type_exoneration ):
                    raise ValidationError('El Cliente es Exonerado y no han ingresado los datos de la exoneración')


    def action_get_payment(self):
        self.validate_pos_order_data()
        return {
            'name': 'Payment',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'pos.make.payment',
            'target': 'new',
        }

    # override para que no genere el monto por redondeo
    def _create_invoice(self, move_vals):
        self.ensure_one()
        new_move = self.env['account.move'].sudo().with_company(self.company_id).with_context(default_move_type=move_vals['move_type']).create(move_vals)
        message = _("This invoice has been created from the point of sale session: <a href=# data-oe-model=pos.order data-oe-id=%d>%s</a>") % (self.id, self.name)
        new_move.message_post(body=message)
        if self.config_id.cash_rounding:
            rounding_applied = float_round(self.amount_paid - self.amount_total,
                                           precision_rounding=new_move.currency_id.rounding)
            rounding_applied = 0     # las facturas a credito no traen ningún rendondeo
            rounding_line = new_move.line_ids.filtered(lambda line: line.is_rounding_line)
            if rounding_line and rounding_line.debit > 0:
                rounding_line_difference = rounding_line.debit + rounding_applied
            elif rounding_line and rounding_line.credit > 0:
                rounding_line_difference = -rounding_line.credit + rounding_applied
            else:
                rounding_line_difference = rounding_applied
            if rounding_applied:
                if rounding_applied > 0.0:
                    account_id = new_move.invoice_cash_rounding_id.loss_account_id.id
                else:
                    account_id = new_move.invoice_cash_rounding_id.profit_account_id.id
                if rounding_line:
                    if rounding_line_difference:
                        rounding_line.with_context(check_move_validity=False).write({
                            'debit': rounding_applied < 0.0 and -rounding_applied or 0.0,
                            'credit': rounding_applied > 0.0 and rounding_applied or 0.0,
                            'account_id': account_id,
                            'price_unit': rounding_applied,
                        })

                else:
                    self.env['account.move.line'].with_context(check_move_validity=False).create({
                        'debit': rounding_applied < 0.0 and -rounding_applied or 0.0,
                        'credit': rounding_applied > 0.0 and rounding_applied or 0.0,
                        'quantity': 1.0,
                        'amount_currency': rounding_applied,
                        'partner_id': new_move.partner_id.id,
                        'move_id': new_move.id,
                        'currency_id': new_move.currency_id if new_move.currency_id != new_move.company_id.currency_id else False,
                        'company_id': new_move.company_id.id,
                        'company_currency_id': new_move.company_id.currency_id.id,
                        'is_rounding_line': True,
                        'sequence': 9999,
                        'name': new_move.invoice_cash_rounding_id.name,
                        'account_id': account_id,
                    })
            else:
                if rounding_line:
                    rounding_line.with_context(check_move_validity=False).unlink()
            if rounding_line_difference:
                existing_terms_line = new_move.line_ids.filtered(
                    lambda line: line.account_id.user_type_id.type in ('receivable', 'payable'))
                if existing_terms_line.debit > 0:
                    existing_terms_line_new_val = float_round(
                        existing_terms_line.debit + rounding_line_difference,
                        precision_rounding=new_move.currency_id.rounding)
                else:
                    existing_terms_line_new_val = float_round(
                        -existing_terms_line.credit + rounding_line_difference,
                        precision_rounding=new_move.currency_id.rounding)
                existing_terms_line.write({
                    'debit': existing_terms_line_new_val > 0.0 and existing_terms_line_new_val or 0.0,
                    'credit': existing_terms_line_new_val < 0.0 and -existing_terms_line_new_val or 0.0,
                })

                new_move._recompute_payment_terms_lines()
        return new_move

    # Factura a crédito
    def action_pos_order_invoice(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError('La Orden de POS debe estar en estado DRAFT (pendiente)')
        elif not self.partner_id:
            raise ValidationError('Para poner a crédito la Factura debe tener un código de cliente')
        if not self.partner_id.property_payment_term_id:
            raise ValidationError('El cliente: %s  no tiene plazo de crédito' %(self.partner_id.name))

        self.validate_pos_order_data()

        # self.write({'to_invoice': True, 'state': 'paid'})
        self.x_name_to_print = self.partner_id.name
        self.x_is_partial = True  
        self.to_invoice = True
        if self.x_cashier_session_id:
            self.session_id = self.x_cashier_session_id
        self.state = 'paid'

        self.genera_consecutivo_dgt()

        res = super(PosOrderInherit, self).action_pos_order_invoice()
        self._create_order_picking()
        self.x_move_id = res.get('res_id')  # move_id creado

        if self.x_document_type:
            self.generate_xml_and_send_dgt(self)
        
        rep_ticket = self.env.ref('pos_extensionfe.pos_order_ticket_report').report_action(self) 
        return rep_ticket


    # Completa la orden de contado
    def process_pos_order_completed(self):
        self.ensure_one()
        if self.x_document_type == 'NC':
            if not self.x_reference_code_id:
                raise  ValidationError('Para la Nota de Crédito se debe indicar el motivo de referencia' )
        elif self.to_invoice:
            # raise ValidationError('No puede procesarse una Venta al Contado por aquí' )
            raise ValidationError('No puede procesarse una Venta a Crédito por aquí' )

        if self.partner_id:
            self.x_name_to_print = self.partner_id.name
        self.x_is_partial = True

        self.action_pos_order_paid()
        self._create_order_picking()

        if self.x_move_type == 'receipt':
            # Es un abono a credito
            payment_method = self.env['account.payment.method'].search([('payment_type', '=', 'inbound'), ('code', '=', 'manual')], limit=1)
            journal_abono = self.session_id.config_id.x_journal_receipt
            for line in self.lines:
                # payment_vals = self.env['account.payment.register'] \
                self.env['account.payment.register'] \
                .with_context(active_model='account.move', active_ids=line.x_move_receipt.id) \
                    .create({
                        'amount': line.x_amount_total_line,
                        'payment_date': fields.Datetime.now(),
                        'payment_type': payment_method.payment_type,
                        'partner_type': 'customer',
                        'journal_id': self.session_id.config_id.x_journal_receipt.id,
                        'currency_id': line.x_move_receipt.currency_id.id,
                        'payment_method_id': payment_method.id,
                        }).sudo().action_create_payments()
        else:
            self.genera_consecutivo_dgt()
            if self.x_document_type:
                self.generate_xml_and_send_dgt(self)
                self.consulta_status_doc_enviado_dgt()

        return {'type': 'ir.actions.act_window_close'}

    # imprime la factura    
    def action_print_ticket_pos_order(self):
        if self._is_pos_order_paid():
            return self.env.ref('pos_extensionfe.pos_order_ticket_report').report_action(self)

    # genera el XML de un documento particular
    def generate_xml_and_send_dgt_manual(self):
        self.ensure_one()
        if self.company_id.x_fae_mode not in ('api-stag', 'api-prod'):
            return
        if self.x_document_type and (not self.x_state_dgt or self.x_state_dgt in ('ENV', 'FI')):
            self.generate_xml_and_send_dgt(self, True)
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
          }

    # genera el XML y envia el documento a la DGT
    def generate_xml_and_send_dgt(self, orders, print_log=False):
        quantity_orders = len(orders)
        count_order = 0
        for inv in orders:
            try:
                count_order += 1

                if not inv.company_id.x_fae_mode or inv.company_id.x_fae_mode == 'N':
                    continue

                osign = -1 if inv.x_move_type == 'refund' else 1

                inv_narration = inv.note
                inv_sucursal = inv.session_id.config_id.x_sucursal
                inv_terminal = inv.session_id.config_id.x_terminal

                if print_log:
                    _logger.info('>> generate_xml_and_send:  - fae_mode: %s,  identif_type: %s, move_type: %s,  pos order: %s'
                                , inv.company_id.x_fae_mode, inv.company_id.x_identification_type_id.code, inv.x_move_type, inv.name )
                if inv.company_id.x_fae_mode == 'api-prod' and not (inv.company_id.x_prod_crypto_key and inv.company_id.x_prod_pin):
                    inv._message_post(subject='Error',
                                    body='generate_xml_and_send:  Aviso!.\n La compañía no tiene configurado parámetros para firmar documentos en PRODUCCION')
                    continue
                elif inv.company_id.x_fae_mode == 'api-stag' and not (inv.company_id.x_test_crypto_key and inv.company_id.x_test_pin):
                    inv._message_post(subject='Error',
                                    body='generate_xml_and_send:  Aviso!.\n La compañía no tiene configurado parámetros para firmar documentos en PRUEBAS')
                    continue

                if print_log:
                    _logger.info('>> generate_xml_and_send:  id: %s   - Invoice: %s / %s ', inv.id, count_order, quantity_orders)

                # if True or (inv.x_document_type == 'FEC' and inv.x_state_dgt == 'RE'):
                if not inv.x_xml_comprobante or inv.x_state_dgt == 'ENV':

                    # previene un error que se dio en un cliente que se genero un Nota de Credito, pero el tipo doc dgt no era NC
                    if inv.x_move_type == 'refund' and inv.x_document_type != 'NC':  # Notas de Crédito
                        inv.x_document_type = 'NC'

                    if not inv.x_currency_rate:
                        if inv.currency_id.name == inv.company_id.currency_id.name:
                            inv.x_currency_rate = 1
                        elif inv.currency_id.rate > 0:
                            inv.x_currency_rate = round(1.0 / inv.currency_id.rate, 2)
                        else:
                            inv.x_currency_rate = None

                    # datos de referencia por si los hay
                    numero_documento_referencia = False
                    fecha_emision_referencia = False
                    tipo_documento_referencia = False
                    codigo_referencia = False
                    razon_referencia = False
                    
                    if inv.x_reference_code_id: 
                        numero_documento_referencia = inv.x_invoice_reference_id.x_electronic_code50
                        fecha_emision_referencia = inv.x_invoice_reference_id.x_issue_date

                        tipo_documento_referencia = inv.x_reference_document_type_id.code
                        codigo_referencia = inv.x_reference_code_id.code
                        razon_referencia =  inv.x_reference_code_id.name

                    lines = dict()
                    otros_cargos = dict()
                    num_otros_cargos = 0
                    num_linea = 0
                    total_otros_cargos = 0.0
                    total_servicio_salon = 0.0
                    total_servicio_gravado = 0.0
                    total_servicio_exento = 0.0
                    total_servicio_exonerado = 0.0
                    total_mercaderia_gravado = 0.0
                    total_mercaderia_exento = 0.0
                    total_mercaderia_exonerado = 0.0
                    total_descuento = 0.0
                    total_impuestos = 0.0
                    total_iva_devuelto = 0.00
                    base_subtotal = 0.0
                    _old_rate_exoneration = False

                    if inv.to_invoice:
                        sale_condition_code = (inv.partner_id.property_payment_term_id.x_sale_condition_id and inv.partner_id.property_payment_term_id.x_sale_condition_id.code or '01')
                    else:
                        sale_condition_code = '01' 

                    if print_log:
                        _logger.info('>> generate_xml_and_send:  order id: %s - name: %s  Procesa lineas', inv.id, inv.name)
                    # procesa las líneas del movimiento
                    for inv_line in inv.lines:
                        
                        # re-valida algunos datos, ya que hubo clientes que brincaron las validaciones del post 
                        if inv_line.product_id and inv_line.product_id.type != 'service' and not (inv_line.product_id.x_cabys_code_id and inv_line.product_id.x_cabys_code_id.code):
                            inv._message_post(subject='Error',
                                                body='El artículo: %s no tiene código CAByS' % (inv_line.product_id.default_code or inv_line.product_id.name) )
                            continue

                        line_price_unit = inv_line.price_unit
                        line_quantity = osign * inv_line.qty
                        line_price_total = osign * inv_line.price_subtotal_incl

                        if inv_line.product_id.x_other_charge_type_id:
                            # Otros Cargos
                            num_otros_cargos += 1
                            otros_cargos[num_otros_cargos] = { 'TipoDocumento': inv_line.product_id.x_other_charge_type_id.code,
                                                                'Detalle': escape(inv_line.name[:150]),
                                                                'MontoCargo': line_price_total
                                                                }
                            if inv_line.x_other_charge_partner_id:
                                otros_cargos[num_otros_cargos]['NombreTercero'] = inv_line.partner_id.name[:100]
                                if inv_line.partner_id.vat:
                                    otros_cargos[num_otros_cargos]['IdentidadTercero'] = inv_line.partner_id.vat

                            total_otros_cargos += line_price_total

                        else:
                            if not line_quantity:
                                continue

                            num_linea += 1

                            # calcula el precio unitario sin el impuesto incluido
                            tax_ids = inv_line.tax_ids
                            if not inv_line.x_tax_ids_for_calc_amount:
                                fpos = inv.fiscal_position_id
                                if fpos:
                                    tax_ids = fpos.map_tax(tax_ids, inv_line.product_id, inv.partner_id)

                            if print_log:
                                _logger.info('>> generate_xml_and_send:  tax_ids: %s  ', str(tax_ids))

                            line_taxes = tax_ids.compute_all(line_price_unit, inv.currency_id, 1.0, product=inv_line.product_id, partner=inv.partner_id)

                            price_unit = round(line_taxes['total_excluded'], 5)
                            base_line = round(price_unit * line_quantity, 5)
                            descuento = inv_line.discount and round(price_unit * line_quantity * inv_line.discount / 100.0, 5) or 0.0

                            subtotal_line = round(base_line - descuento, 5)

                            # Elimina la doble comilla en la descripción, por eje. Tabla de 1" x 3" (la doble comilla usada para referirse a pulgada)
                            detalle_linea = inv_line.full_product_name
                            if not detalle_linea and inv_line.product_id:
                                detalle_linea = inv_line.product_id.name or '.'
                            detalle_linea = detalle_linea[:160].replace('"', '')

                            line = {
                                    "cantidad": line_quantity,
                                    "detalle": escape(detalle_linea),
                                    "precioUnitario": price_unit,
                                    "montoTotal": base_line,
                                    "subtotal": subtotal_line,
                                    "BaseImponible": subtotal_line,
                                    "unidadMedida": inv_line.product_uom_id and inv_line.product_uom_id.x_code_dgt or 'Sp'
                                    }

                            if inv_line.product_id:
                                line["codigo"] = inv_line.product_id.default_code or ''
                                if inv_line.product_id.x_cabys_code_id:
                                    line["codigoCabys"] = inv_line.product_id.x_cabys_code_id.code


                            if inv_line.discount and price_unit > 0:
                                total_descuento += descuento
                                line["montoDescuento"] = descuento
                                line["naturalezaDescuento"] = inv_line.x_discount_note or 'Descuento Comercial'


                            # Se generan los impuestos
                            taxes = dict()
                            acum_line_tax = 0.0
                            has_exoneration = False
                            perc_exoneration = 0
                            include_baseImponible = False
                            factor_exoneracion = 0.0   #  relacion respecto al total del IVA, se calcula asi:  porc_exoneracion / porcentaje de IVA 
                            if tax_ids:
                                itax = 0
                                taxes_lookup = {}
                                for tx in tax_ids:
                                    if inv.partner_id.x_special_tax_type == 'E' and tx.x_has_exoneration:
                                        # Partner Exonerado
                                        has_exoneration = True
                                        perc_exoneration = (tx.x_exoneration_rate or 0)
                                        tax_rate = tx.amount + perc_exoneration
                                        factor_exoneracion = perc_exoneration / tax_rate
                                        taxes_lookup[tx.id] = {'cod_impuesto': tx.x_tax_code_id.code, 
                                                              'tarifa': tax_rate,
                                                              'cod_tarifa_imp': tx.x_tax_rate_id.code,
                                                              'porc_exoneracion': perc_exoneration,  }
                                    else:
                                        tax_rate = tx.amount
                                        taxes_lookup[tx.id] = {'cod_impuesto': tx.x_tax_code_id.code, 
                                                              'tarifa': tax_rate,
                                                              'cod_tarifa_imp': tx.x_tax_rate_id.code,
                                                              'porc_exoneracion': None,  }
                                    
                                    if not tx.x_tax_code_id or not tx.x_tax_rate_id:
                                        raise UserError('Para el impuesto: %s, no tiene definido el código de impuesto de Hacienda o el códito de tarifa' %(tx.name) )
                                    elif tx.x_tax_rate_id.code == '08' and tax_rate != 13:
                                        raise UserError('Para el artículo: %s, el código de tarifa "08", el porcentaje de interes debe ser 13, pero es: %s' 
                                                        %(inv_line.product_id.default_code, str(tax_rate)) )

                                    include_baseImponible = (tx.x_tax_code_id.code == '07')

                                for i in line_taxes['taxes']:
                                    # calcula el detalle de impuestos
                                    if taxes_lookup[i['id']]['cod_impuesto'] != '00':  # No 00=Exento
                                        itax += 1
                                        tax_amount = round(subtotal_line * taxes_lookup[i['id']]['tarifa'] / 100, 2)
                                        acum_line_tax += tax_amount
                                        tax = {
                                            'codigo': taxes_lookup[i['id']]['cod_impuesto'],
                                            'tarifa': taxes_lookup[i['id']]['tarifa'],
                                            'monto': tax_amount,
                                            'cod_tarifa_imp': taxes_lookup[i['id']]['cod_tarifa_imp'],
                                        }
                                        # Se genera la exoneración si existe para este impuesto
                                        if has_exoneration:                                            
                                            perc_exoneration = taxes_lookup[i['id']]['porc_exoneracion']
                                            tax_amount_exo = round(subtotal_line * (perc_exoneration / 100), 2)
                                            if tax_amount_exo > tax_amount:
                                                tax_amount_exo = tax_amount

                                            acum_line_tax -= tax_amount_exo  # resta la exoneracion al acumulado de impuesto
                                            tax["exoneracion"] = { "monto_exonera": tax_amount_exo,
                                                                   "porc_exonera": perc_exoneration}

                                        taxes[itax] = tax

                                line["impuesto"] = taxes
                                line["impuestoNeto"] = round(acum_line_tax, 5)

                            if include_baseImponible and inv.x_document_type != 'FEE':
                                line["BaseImponible"] = subtotal_line


                            total_impuestos += acum_line_tax

                            # calcula la distribucion de monto gravados, exonerado y exento
                            if taxes:
                                monto_exento = 0.0
                                if has_exoneration and factor_exoneracion > 0:
                                    monto_exonerado = base_line if factor_exoneracion >= 1 else round(base_line * factor_exoneracion, 5)
                                    monto_gravado = base_line - monto_exonerado
                                else:
                                    monto_gravado = base_line                            
                                    monto_exonerado = 0
                            else:
                                monto_exento = base_line
                                monto_exonerado = 0
                                monto_gravado = 0

                            if inv_line.product_id.type == 'service' or inv_line.product_uom_id.category_id.name in ('Services', 'Servicios'):                                 
                                total_servicio_gravado += monto_gravado
                                total_servicio_exonerado += monto_exonerado
                                total_servicio_exento += monto_exento
                            else:
                                total_mercaderia_gravado += monto_gravado
                                total_mercaderia_exonerado += monto_exonerado
                                total_mercaderia_exento += monto_exento

                            base_subtotal += subtotal_line

                            line["montoTotalLinea"] = round(subtotal_line + acum_line_tax, 5)

                            lines[num_linea] = line

                    if print_log:
                        _logger.info('>> generate_xml_and_send:  totales: %s  ', base_subtotal)

                    total_xml = base_subtotal + total_impuestos + total_otros_cargos - total_iva_devuelto
                    if abs(total_xml - (osign * inv.amount_total)) > 0.5:
                        # inv.state_tributacion = 'error'
                        inv._message_post(
                            subject='Error',
                            body='Monto factura no concuerda con monto para XML. Factura: %s total XML:%s  base:%s impuestos:%s otros_cargos:%s iva_devuelto:%s' % (
                                  inv.amount_total, total_xml, base_subtotal, total_impuestos, total_otros_cargos, total_iva_devuelto) )
                        continue

                    # Genera el consecutivo y clave de 50
                    if inv.x_document_type and not inv.x_electronic_code50:
                        inv.genera_consecutivo_dgt()

                    #
                    total_servicio_gravado = round(total_servicio_gravado, 5)
                    total_servicio_exento = round(total_servicio_exento, 5)
                    total_servicio_exonerado = round(total_servicio_exonerado, 5)
                    total_mercaderia_gravado = round(total_mercaderia_gravado, 5)
                    total_mercaderia_exento = round(total_mercaderia_exento, 5)
                    total_mercaderia_exonerado = round(total_mercaderia_exonerado, 5)
                    total_otros_cargos = round(total_otros_cargos, 5)
                    total_iva_devuelto = round(total_iva_devuelto, 5)
                    base_subtotal = round(base_subtotal, 5)
                    total_impuestos = round(total_impuestos, 5)
                    total_descuento = round(total_descuento, 5)

                    if inv.company_id.x_situacion_comprobante == '1':
                        # crea el XML 
                        if print_log:
                            _logger.info('>> generate_xml_and_send: generando el xml del doc id: %s', inv.id)
                        try:
                            xml_str = fae_utiles.gen_xml_v43( inv, sale_condition_code, total_servicio_gravado, total_servicio_exento, total_servicio_exonerado
                                                            ,total_mercaderia_gravado, total_mercaderia_exento, total_mercaderia_exonerado
                                                            ,total_otros_cargos, total_iva_devuelto, base_subtotal, total_impuestos, total_descuento
                                                            ,json.dumps(lines, ensure_ascii=False)
                                                            ,otros_cargos, inv.x_currency_rate, inv_narration
                                                            ,tipo_documento_referencia, numero_documento_referencia
                                                            ,fecha_emision_referencia, codigo_referencia, razon_referencia
                                                            )
                        except Exception as error:
                            raise Exception('Falla ejecutando FAE_UTILES.GEN_XML_V43, error: ' + str(error))

                        # _logger.info('>> generate_xml_and_send:  XML generado:  xml:%s', xml_str)

                        if inv.company_id.x_fae_mode == 'api-prod':
                            xml_firmado = fae_utiles.sign_xml(inv.company_id.x_prod_crypto_key, inv.company_id.x_prod_pin, xml_str)
                        else:
                            xml_firmado = fae_utiles.sign_xml(inv.company_id.x_test_crypto_key, inv.company_id.x_test_pin, xml_str)

                        # _logger.info('>> generate_xml_and_send:  XML firmado: %s', xml_firmado)

                        inv.x_xml_comprobante_fname = fae_utiles.get_inv_fname(inv) + '.xml'
                        inv.x_xml_comprobante = base64.encodebytes(xml_firmado)

                else:
                    xml_firmado = inv.x_xml_comprobante
                
                if inv.company_id.x_situacion_comprobante != '1':
                    # la comunicación con hacienda no esta en modo Normal
                    # _logger.info('>> generate_xml_and_send: Documento %s generado sin comunicación con Hacienda', inv.x_sequence)
                    inv._message_post(subject='Note', body='Documento ' + inv.x_sequence + ' generado sin comunicación con la DGT')
                    continue

                # envia el XML firmado
                if inv.x_state_dgt == '1':
                    response_status = 400
                    response_text = 'ya había sido enviado a la DGT'
                else:
                    response_json = fae_utiles.send_xml_fe(inv, inv.x_issue_date, xml_firmado, inv.company_id.x_fae_mode)                
                    response_status = response_json.get('status')
                    response_text = response_json.get('text')

                if 200 <= response_status <= 299:
                    inv.x_state_dgt = 'PRO'
                    inv._message_post(subject='Note', body='Documento ' + inv.x_sequence + ' enviado a la DGT')
                    
                    time.sleep(4)   # espera 5 segundos antes de consultar por el status de hacienda
                    inv.consulta_status_doc_enviado_dgt()

                else:
                    if response_text.find('ya fue recibido anteriormente') != -1:
                        inv.x_state_dgt = 'PRO'
                        inv._message_post(subject='Error', body='DGT: Documento recibido anteriormente, queda en espera de respuesta de hacienda')
                    elif inv.x_error_count > 10:
                        inv._message_post(subject='Error', body='DGT: ' + response_text)
                        inv.x_state_dgt = 'ERR'
                        # _logger.error('>> generate_xml_and_send: Invoice: %s  Status: %s Error sending XML: %s' % (inv.x_electronic_code50, response_status, response_text))
                    else:
                        inv.x_error_count += 1
                        inv.x_state_dgt = 'PRO'
                        inv._message_post(subject='Error', body='DGT: status: %s, text: %s ' % (response_status, response_text) )
                        # _logger.error('>> generate_xml_and_send: Invoice: %s  Status: %s Error sending XML: %s' % (inv.x_electronic_code50, response_status, response_text))

            except Exception as error:
                inv._message_post( subject='Error',
                                body='generate_xml_and_send.exception:  Aviso!.\n Error : '+ str(error))
                continue

    # Para sobre escribir en cada instalación cuando los clientes quieran un desarrollo adicional
    # El texto devuelto debe ser un elemento XML bien formado con nodo "OtroTexto" u "OtroContenido"
    def xml_OtroTexto(self):
        otro_texto = None
        # if self.ref:
        #     otro_texto = '<OtroTexto %s="%s">%s</OtroTexto>' % ('codigo', 'NumeroOrden', escape(self.ref))
        return otro_texto

    # cron Job: Chequea en hacienda el status de documentos enviados
    def _check_status_pos_order_enviados(self, max_invoices=20):
        orders = self.env['pos.order'].search(
                                        [('state', 'in', ('paid','done','invoiced')),
                                         ('x_state_dgt', '=', 'PRO')], 
                                        limit=max_invoices)
        _logger.info('>> _check_status_pos_order_enviados: Cantidad %s', len(orders))
        if orders:
            orders.consulta_status_doc_enviado_dgt()

    def consulta_status_doc_enviado_dgt(self):
        for inv in self:
            if not inv.company_id.x_fae_mode or inv.company_id.x_fae_mode == 'N':
                continue
            state_dgt_ant = inv.x_state_dgt
            state_dgt = inv.x_state_dgt
            if inv.x_state_dgt == '1':
                state_dgt = inv.x_state_dgt
            else:
                _logger.info('>> consulta_status_doc_enviado_dgt: %s -  %s', inv.x_document_type, inv.x_sequence)
                if not inv.x_xml_comprobante_fname:
                    inv.x_xml_comprobante_fname = fae_utiles.get_inv_fname(inv) + '.xml'

                try:
                    token_dgt = fae_utiles.get_token_hacienda(inv.company_id, inv.company_id.x_fae_mode)
                    state_dgt = fae_utiles.consulta_doc_enviado(inv, token_dgt, inv.company_id.x_fae_mode)
                except:
                    pass
            
            if state_dgt == '1' and (not inv.x_state_email or inv.x_state_email != 'E'):
                inv.action_send_mail_fae()

            if state_dgt_ant != state_dgt and inv.x_move_id:
                # cambio el estado dgt, así que actualiza los datos en el invoice 
                if not inv.x_move_id.x_electronic_code50:
                    inv.x_move_id.x_document_type = inv.x_document_type
                    inv.x_move_id.x_sequence = inv.x_sequence
                    inv.x_move_id.x_electronic_code50 = inv.x_electronic_code50
                    inv.name = inv.x_sequence
                if state_dgt in ('1','2'):
                    inv.x_move_id.x_state_dgt = state_dgt

    # Función para adjuntar los documentos y emviar correo al email del cliente
    def action_send_mail_fae(self):
        self.ensure_one()

        # si no hay el mensaje de respuesta, no envia el correo
        if not self.x_xml_respuesta_fname or self.x_state_dgt != '1':
            return

        try:
            new_state_email = fae_utiles.send_mail_fae(self, 'pos_extensionfe.fae_pos_order_email_template')
            if new_state_email == 'E':
                self.message_post(subject='Note', body='Documento ' + self.x_sequence + ' enviado al correo: ' + self.partner_id.email )
            if not self.x_state_email or (self.x_state_email == 'SC' and new_state_email == 'E'):
                self.x_state_email = new_state_email
        except UserError as error:
            raise UserError('>> '+str(error))
        except Exception as error:
            self.message_post(subject='Error', body='Archivos de XMLs y PDF del documento ' + self.x_sequence + ' no pudieron ser enviados al correo del cliente ')
            # raise UserError('XML del documento no ha sido generado')

    # Función para adjuntar los documentos y emviar correo al email del cliente
    def action_send_mail_fae_ant(self):
        self.ensure_one()

        # si no hay el mensaje de respuesta, no envia el correo
        if not self.x_xml_respuesta_fname or self.x_state_dgt != '1':
            return

        email_template_id = self.env.ref('pos_extensionfe.fae_pos_order_email_template', raise_if_not_found=False).id

        if email_template_id and self.partner_id:
            new_state_email = self.x_state_email
            template = self.env['mail.template'].browse(email_template_id)

            if not self.partner_id.email:
                new_state_email = 'SC' if not self.x_state_email else self.x_state_email
            else: 
                attachment = self.env['ir.attachment'].search([('res_model', '=', 'pos.order'),
                                                               ('res_id', '=', self.id),
                                                               ('res_field', '=', 'x_xml_comprobante')],
                                                              order='id desc', limit=1)
                if attachment:
                    attachment.name = self.x_xml_comprobante_fname
                    attachment_resp = self.env['ir.attachment'].search([('res_model', '=', 'pos.order'),
                                                                        ('res_id', '=', self.id),
                                                                        ('res_field', '=', 'x_xml_respuesta')],
                                                                       order='id desc', limit=1)
                    if attachment_resp:
                        attachment_resp.name = self.x_xml_respuesta_fname
                        template.attachment_ids = [(6, 0, [attachment.id, attachment_resp.id])]

                    template.send_mail(self.id, force_send=True)
                    new_state_email = 'E'
                else:
                    raise UserError('XML del documento no ha sido generado')

            if not self.x_state_email or (self.x_state_email == 'SC' and new_state_email == 'E'):
                self.x_state_email = new_state_email

