# -*- coding: utf-8 -*-
# Part of Scalebox All-in-One ERP.
# Copyright (C) 2026 Scalebox For Digital Services. All Rights Reserved.

from odoo import api, fields, models, _


class ScaleboxDashboard(models.Model):
    """Interactive live dashboard: KPIs computed over a selectable date range,
    with drill-down actions to the underlying documents."""

    _name = 'scalebox.dashboard'
    _description = 'Scalebox - Dashboard'

    name = fields.Char(default='Dashboard', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    date_from = fields.Date(
        string='From Date',
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string='To Date', default=fields.Date.context_today)

    # --- Sales ---
    sales_today = fields.Monetary(string='Today Sales', compute='_compute_kpis')
    sales_period = fields.Monetary(string='Sales (Period)', compute='_compute_kpis')
    sales_count = fields.Integer(string='Sales Count', compute='_compute_kpis')
    sale_returns_period = fields.Monetary(string='Sales Returns (Period)', compute='_compute_kpis')
    net_sales_period = fields.Monetary(string='Net Sales (Period)', compute='_compute_kpis')
    # --- POS ---
    pos_sales_today = fields.Monetary(string='POS Sales (Today)', compute='_compute_kpis')
    pos_sales_period = fields.Monetary(string='POS Sales (Period)', compute='_compute_kpis')
    # --- Purchases / Expenses ---
    purchases_period = fields.Monetary(string='Purchases (Period)', compute='_compute_kpis')
    purchase_returns_period = fields.Monetary(string='Purchase Returns (Period)', compute='_compute_kpis')
    purchases_count = fields.Integer(string='Purchases Count', compute='_compute_kpis')
    expenses_period = fields.Monetary(string='Expenses (Period)', compute='_compute_kpis')
    expenses_count = fields.Integer(string='Expenses Count', compute='_compute_kpis')
    # --- Operational ---
    net_period = fields.Monetary(
        string='Net of the Period (After Returns & Expenses)', compute='_compute_kpis')
    # --- Financial positions (as of today) ---
    cash_bank_balance = fields.Monetary(string='Cash & Bank Balance', compute='_compute_kpis')
    receivable_total = fields.Monetary(string='Customer Receivables', compute='_compute_kpis')
    payable_total = fields.Monetary(string='Vendor Payables', compute='_compute_kpis')

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    def _period_domain(self, rec):
        return [
            ('state', '=', 'done'),
            ('company_id', '=', (rec.company_id or self.env.company).id),
            ('date', '>=', rec.date_from),
            ('date', '<=', rec.date_to),
        ]

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_kpis(self):
        today = fields.Date.context_today(self)
        Sale = self.env['scalebox.easy.sale']
        SaleReturn = self.env['scalebox.easy.sale.return']
        Purchase = self.env['scalebox.easy.purchase']
        PurchaseReturn = self.env['scalebox.easy.purchase.return']
        Expense = self.env['scalebox.expense']
        PosOrder = self.env['pos.order']
        Aml = self.env['account.move.line']

        for rec in self:
            company = rec.company_id or self.env.company
            if not rec.date_from or not rec.date_to:
                rec.date_from = today.replace(day=1)
                rec.date_to = today
            dom = self._period_domain(rec)

            sales = Sale.search(dom)
            rec.sales_period = sum(sales.mapped('amount_total'))
            rec.sales_count = len(sales)
            rec.sales_today = sum(Sale.search([
                ('state', '=', 'done'), ('company_id', '=', company.id),
                ('date', '=', today)]).mapped('amount_total'))

            sale_returns = SaleReturn.search(dom)
            rec.sale_returns_period = sum(sale_returns.mapped('amount_total'))
            rec.net_sales_period = rec.sales_period - rec.sale_returns_period

            purchases = Purchase.search(dom)
            rec.purchases_period = sum(purchases.mapped('amount_total'))
            rec.purchases_count = len(purchases)
            purchase_returns = PurchaseReturn.search(dom)
            rec.purchase_returns_period = sum(purchase_returns.mapped('amount_total'))

            expenses = Expense.search(dom)
            rec.expenses_period = sum(expenses.mapped('amount'))
            rec.expenses_count = len(expenses)

            rec.net_period = (rec.net_sales_period
                              - (rec.purchases_period - rec.purchase_returns_period)
                              - rec.expenses_period)

            pos_base = [('company_id', '=', company.id),
                        ('state', 'in', ('paid', 'done', 'invoiced'))]
            rec.pos_sales_today = sum(PosOrder.search(
                pos_base + [('date_order', '>=', fields.Datetime.to_datetime(today))]
            ).mapped('amount_total'))
            rec.pos_sales_period = sum(PosOrder.search(pos_base + [
                ('date_order', '>=', fields.Datetime.to_datetime(rec.date_from)),
                ('date_order', '<', fields.Datetime.add(
                    fields.Datetime.to_datetime(rec.date_to), days=1)),
            ]).mapped('amount_total'))

            aml_base = [('parent_state', '=', 'posted'),
                        ('company_id', '=', company.id)]
            cash = Aml.read_group(
                aml_base + [('account_id.account_type', '=', 'asset_cash')],
                ['balance:sum'], [])
            rec.cash_bank_balance = (cash[0]['balance'] or 0.0) if cash else 0.0
            receivable = Aml.read_group(
                aml_base + [('account_id.account_type', '=', 'asset_receivable')],
                ['balance:sum'], [])
            rec.receivable_total = (receivable[0]['balance'] or 0.0) if receivable else 0.0
            payable = Aml.read_group(
                aml_base + [('account_id.account_type', '=', 'liability_payable')],
                ['balance:sum'], [])
            rec.payable_total = -((payable[0]['balance'] or 0.0) if payable else 0.0)

    def action_refresh(self):
        return True

    # ------------------------------------------------------------------
    # Drill-down actions
    # ------------------------------------------------------------------
    def _drill(self, name, model, domain, views='list,form', extra_ctx=None):
        self.ensure_one()
        ctx = {'create': False}
        ctx.update(extra_ctx or {})
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': views,
            'domain': domain,
            'context': ctx,
        }

    def action_open_sales(self):
        return self._drill(_('Sales Operations'), 'scalebox.easy.sale',
                           self._period_domain(self))

    def action_open_sale_returns(self):
        return self._drill(_('Sales Returns'), 'scalebox.easy.sale.return',
                           self._period_domain(self))

    def action_open_purchases(self):
        return self._drill(_('Purchase Operations'), 'scalebox.easy.purchase',
                           self._period_domain(self))

    def action_open_purchase_returns(self):
        return self._drill(_('Purchase Returns'), 'scalebox.easy.purchase.return',
                           self._period_domain(self))

    def action_open_expenses(self):
        return self._drill(_('Expenses'), 'scalebox.expense',
                           self._period_domain(self))

    def action_open_pos_orders(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        return self._drill(_('POS Orders'), 'pos.order', [
            ('company_id', '=', company.id),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('date_order', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('date_order', '<', fields.Datetime.add(
                fields.Datetime.to_datetime(self.date_to), days=1)),
        ])

    def action_open_receivables(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        return self._drill(_('Customer Receivables'), 'account.move.line', [
            ('parent_state', '=', 'posted'), ('company_id', '=', company.id),
            ('account_id.account_type', '=', 'asset_receivable'),
        ], views='list,pivot')

    def action_open_payables(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        return self._drill(_('Vendor Payables'), 'account.move.line', [
            ('parent_state', '=', 'posted'), ('company_id', '=', company.id),
            ('account_id.account_type', '=', 'liability_payable'),
        ], views='list,pivot')

    def action_open_cash(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        return self._drill(_('Cash & Bank Movements'), 'account.move.line', [
            ('parent_state', '=', 'posted'), ('company_id', '=', company.id),
            ('account_id.account_type', '=', 'asset_cash'),
        ], views='list,pivot')

    def action_open_analytics(self):
        self.ensure_one()
        return self._drill(_('Unified Analytics (Charts)'), 'scalebox.report', [
            ('state', '=', 'done'),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ], views='graph,pivot,list')
