# -*- coding: utf-8 -*-
# Part of Scalebox All-in-One ERP.
# Copyright (C) 2026 Scalebox For Digital Services. All Rights Reserved.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ScaleboxExpenseType(models.Model):
    """Configure expense types and map them to chart of accounts."""

    _name = 'scalebox.expense.type'
    _description = 'Scalebox - Expense Type'
    _order = 'name'

    name = fields.Char(string='Expense Name', required=True, translate=True)
    account_id = fields.Many2one(
        'account.account', string='Account', required=True,
        check_company=True,
        domain="[('account_type', 'in', ('expense', 'expense_depreciation', 'expense_direct_cost'))]",
        help='The expense account to be debited when posting the expense.')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         'This expense name already exists in this company.'),
    ]


class ScaleboxExpense(models.Model):
    """Expense screen: pick the type and payment method; the system posts the entry
    automatically and prints a payment voucher."""

    _name = 'scalebox.expense'
    _description = 'Scalebox - Expense'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Voucher Number', default=lambda self: _('New'),
        copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency', readonly=True)
    date = fields.Date(
        string='Date', required=True,
        default=fields.Date.context_today)
    expense_type_id = fields.Many2one(
        'scalebox.expense.type', string='Expense Type', required=True,
        check_company=True, tracking=True)
    description = fields.Char(string='Description', required=True)
    partner_id = fields.Many2one(
        'res.partner', string='Beneficiary / Recipient',
        help='Optional: the employee or party receiving the amount.')
    amount = fields.Monetary(string='Amount', required=True, tracking=True)
    pay_method = fields.Selection([
        ('cash_bank', 'Cash / Bank'),
        ('custody', 'Custody'),
    ], string='Payment Method', required=True, default='cash_bank')
    journal_id = fields.Many2one(
        'account.journal', string='Cash / Bank', check_company=True,
        domain="[('type', 'in', ('bank', 'cash'))]")
    custody_account_id = fields.Many2one(
        'account.account', string='Custody Account', check_company=True,
        domain="[('account_type', 'in', ('asset_current', 'asset_cash'))]",
        help='The custody account to be credited.')
    move_id = fields.Many2one(
        'account.move', string='Journal Entry', readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Posted'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)
    user_id = fields.Many2one(
        'res.users', string='Responsible', required=True,
        default=lambda self: self.env.user)
    note = fields.Text(string='Notes')

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_('Expense amount must be greater than zero.'))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'scalebox.expense') or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'done' for rec in self):
            raise UserError(_('Cannot delete a posted expense. Cancel it first.'))
        return super().unlink()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Posts the expense: debit expense account / credit cash, bank or custody."""
        for rec in self:
            if rec.state != 'draft':
                continue
            credit_account, journal = rec._get_credit_account_and_journal()
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': rec.date,
                'ref': '%s - %s' % (rec.name, rec.description),
                'company_id': rec.company_id.id,
                'line_ids': [
                    (0, 0, {
                        'account_id': rec.expense_type_id.account_id.id,
                        'partner_id': rec.partner_id.id,
                        'name': rec.description,
                        'debit': rec.amount,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'account_id': credit_account.id,
                        'partner_id': rec.partner_id.id,
                        'name': rec.description,
                        'debit': 0.0,
                        'credit': rec.amount,
                    }),
                ],
            })
            move.action_post()
            rec.move_id = move
            rec.state = 'done'
            rec.message_post(body=_('Expense posted with journal entry %s', move.name))
        return True

    def action_cancel(self):
        if not self.env.user.has_group('scalebox_aio.group_scalebox_manager'):
            raise UserError(_('Cancelling operations is restricted to managers only.'))
        for rec in self:
            if rec.move_id and rec.move_id.state == 'posted':
                rec.move_id.button_draft()
                rec.move_id.button_cancel()
            rec.state = 'cancel'
        return True

    def action_draft(self):
        if not self.env.user.has_group('scalebox_aio.group_scalebox_manager'):
            raise UserError(_('This action is restricted to managers only.'))
        for rec in self:
            if rec.state != 'cancel':
                raise UserError(_('Only cancelled expenses can be reset to draft.'))
            rec.state = 'draft'
        return True

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No journal entry yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    def action_print_receipt(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Post the expense before printing the voucher.'))
        return self.env.ref(
            'scalebox_aio.action_report_expense_receipt').report_action(self)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_credit_account_and_journal(self):
        self.ensure_one()
        if self.pay_method == 'cash_bank':
            if not self.journal_id:
                raise UserError(_('Select a cash or bank journal.'))
            if not self.journal_id.default_account_id:
                raise UserError(_(
                    'Journal %s has no default account. Check the journal settings.',
                    self.journal_id.name))
            return self.journal_id.default_account_id, self.journal_id
        # Custody: the entry is posted in the miscellaneous journal
        if not self.custody_account_id:
            raise UserError(_('Select the custody account.'))
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_('No miscellaneous journal found in this company.'))
        return self.custody_account_id, journal

    def _amount_in_words(self):
        self.ensure_one()
        return self.currency_id.amount_to_text(self.amount)
