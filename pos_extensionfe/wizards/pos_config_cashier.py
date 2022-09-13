# -*- coding: utf-8 -*-
from odoo import fields, models, _, api
from odoo.exceptions import Warning, UserError, ValidationError


class xpos_config_cashier(models.TransientModel):
    _name = 'xpos.config_cashier'
    _description = 'Pos Config Cashier'

    config_id = fields.Many2one('pos.config', string='Config', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True, default=lambda x: x.env.company.currency_id)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    password = fields.Char(string='Contraseña')
    balance_start = fields.Monetary('Fondo inicia de caja', currency_field='currency_id')
    started_session = fields.Boolean()
    is_variable = fields.Boolean(related='employee_id.x_cash_starting_variable', readonly=True)

    def get_session(self):
        return self.env['pos.session'].search([('config_id', '=', self.config_id.id), ('state', '=', 'opened'), ('x_employee_id', '=', self.employee_id.id)],
                                              order='id desc', limit=1)

    @api.onchange('employee_id')
    def set_balance_start(self):
        session = self.get_session()
        if not session:
            self.balance_start = self.employee_id.x_cash_starting_amount
            self.started_session = False
        else:
            self.started_session = True
            self.balance_start = session.cash_register_balance_start

    def check_cashier(self, config, employee):
        employees = config.employee_ids
        for emp in employees:
            if emp.id == employee.id:
                return True
        return False

    def action_config_cashier_select(self):
        self.ensure_one()
        config = self.config_id
        # pueden haber varios puntos de venta por lo que el cajero solo debe ver las sessiones del punto de venta conectado
        sessions = self.env['pos.session'].search([('config_id', '=', config.id)]).ids
        employee = self.employee_id
        if self.check_cashier(config, employee):
            if self.employee_id.x_password == self.password:
                # cashier_session = self.env['pos.session'].search([('config_id', '=', config.id),('state','=','opened'),('x_employee_id','=', employee.id)], order='id desc', limit=1)
                cashier_session = self.get_session()
                if not cashier_session:
                    # crear una nueva session para el Cajero (en rescue para poder tener varias sessiones abiertas)
                    values = {
                            'user_id': self.env.uid,
                            'config_id': config.id,
                            'state': 'opened',
                            'x_employee_id': employee.id,
                            'start_at': fields.Datetime.now(),
                            'rescue': True,
                            }
                    res = self.env['pos.session'].create(values)
                    res.cash_register_id.previous_statement_id = None
                    res.cash_register_id.balance_start = self.balance_start
                    cashier_session = res

                tree_view = self.env.ref('pos_extensionfe.pos_extfe_pos_order_tree_view')
                form_view = self.env.ref('pos_extensionfe.pos_extfe_pos_order_form_view')
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Cajero: ' + employee.name.upper()),
                    'res_model': 'pos.order',
                    'view_mode': 'list',
                    'context': {'search_default_state_draft': 1, 'cashier_id': employee.id, 'cashier_session_id': cashier_session.id},
                    'views': [(tree_view.id, 'list'), (form_view.id, 'form')],
                    'domain': [('session_id', 'in', sessions), ('state', '!=', 'cancel')],
                }

            else:
                raise Warning('Acceso Denegado: Su clave no es correcta')
        else:
            raise Warning('Acceso Denegado: Usted no tiene acceso a este Punto de Venta')
        return True

    def action_config_cashier_close(self):
        self.ensure_one()
        config = self.config_id
        employee = self.employee_id
        if self.check_cashier(config, employee):
            if self.employee_id.x_password == self.password:
                cashier_session = self.env['pos.session'].search([('config_id', '=', config.id), ('state', '=', 'opened'), ('x_employee_id', '=', employee.id)],
                                                                 order='id asc', limit=1)
                if not cashier_session:
                    raise Warning('El cajero no tiene ninguna Caja abierta')
                return {
                    'name': _('Session'),
                    'view_mode': 'form,tree',
                    'res_model': 'pos.session',
                    'res_id': cashier_session.id,
                    'view_id': False,
                    'type': 'ir.actions.act_window',
                }
            else:
                raise Warning('Acceso Denegado: Su clave no es correcta')
        else:
            raise Warning('Acceso Denegado: Usted no tiene acceso a este Punto de Venta')
        return True
