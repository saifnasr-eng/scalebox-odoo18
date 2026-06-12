# -*- coding: utf-8 -*-
# Part of Scalebox All-in-One ERP.
# Copyright (C) 2026 Scalebox For Digital Services. All Rights Reserved.

from odoo import fields, models, tools


class ScaleboxReport(models.Model):
    """Unified analytics view for sales and purchases (SQL view - read only)."""

    _name = 'scalebox.report'
    _description = 'Scalebox - Analytics'
    _auto = False
    _order = 'date desc'

    doc_type = fields.Selection([
        ('sale', 'Sale'),
        ('purchase', 'Purchase'),
        ('expense', 'Expense'),
        ('sale_return', 'Sales Return'),
        ('purchase_return', 'Purchase Return'),
        ('pos', 'POS'),
    ], string='Operation Type', readonly=True)
    name = fields.Char(string='Reference', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer / Vendor', readonly=True)
    user_id = fields.Many2one('res.users', string='Responsible', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    amount_untaxed = fields.Monetary(string='Untaxed', readonly=True)
    amount_total = fields.Monetary(string='Total', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Confirmed'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    s.id AS id,
                    'sale' AS doc_type,
                    s.name AS name,
                    s.date AS date,
                    s.partner_id AS partner_id,
                    s.user_id AS user_id,
                    s.company_id AS company_id,
                    c.currency_id AS currency_id,
                    s.amount_untaxed AS amount_untaxed,
                    s.amount_total AS amount_total,
                    s.state AS state
                FROM scalebox_easy_sale s
                JOIN res_company c ON c.id = s.company_id

                UNION ALL

                SELECT
                    p.id + 1000000000 AS id,
                    'purchase' AS doc_type,
                    p.name AS name,
                    p.date AS date,
                    p.partner_id AS partner_id,
                    p.user_id AS user_id,
                    p.company_id AS company_id,
                    c.currency_id AS currency_id,
                    p.amount_untaxed AS amount_untaxed,
                    p.amount_total AS amount_total,
                    p.state AS state
                FROM scalebox_easy_purchase p
                JOIN res_company c ON c.id = p.company_id

                UNION ALL

                SELECT
                    e.id + 2000000000 AS id,
                    'expense' AS doc_type,
                    e.name AS name,
                    e.date AS date,
                    e.partner_id AS partner_id,
                    e.user_id AS user_id,
                    e.company_id AS company_id,
                    c.currency_id AS currency_id,
                    e.amount AS amount_untaxed,
                    e.amount AS amount_total,
                    e.state AS state
                FROM scalebox_expense e
                JOIN res_company c ON c.id = e.company_id

                UNION ALL

                SELECT
                    sr.id + 3000000000 AS id,
                    'sale_return' AS doc_type,
                    sr.name AS name,
                    sr.date AS date,
                    sr.partner_id AS partner_id,
                    sr.user_id AS user_id,
                    sr.company_id AS company_id,
                    c.currency_id AS currency_id,
                    sr.amount_untaxed AS amount_untaxed,
                    sr.amount_total AS amount_total,
                    sr.state AS state
                FROM scalebox_easy_sale_return sr
                JOIN res_company c ON c.id = sr.company_id

                UNION ALL

                SELECT
                    pr.id + 4000000000 AS id,
                    'purchase_return' AS doc_type,
                    pr.name AS name,
                    pr.date AS date,
                    pr.partner_id AS partner_id,
                    pr.user_id AS user_id,
                    pr.company_id AS company_id,
                    c.currency_id AS currency_id,
                    pr.amount_untaxed AS amount_untaxed,
                    pr.amount_total AS amount_total,
                    pr.state AS state
                FROM scalebox_easy_purchase_return pr
                JOIN res_company c ON c.id = pr.company_id

                UNION ALL

                SELECT
                    po.id + 5000000000 AS id,
                    'pos' AS doc_type,
                    po.name AS name,
                    po.date_order::date AS date,
                    po.partner_id AS partner_id,
                    po.user_id AS user_id,
                    po.company_id AS company_id,
                    c.currency_id AS currency_id,
                    (po.amount_total - po.amount_tax) AS amount_untaxed,
                    po.amount_total AS amount_total,
                    'done' AS state
                FROM pos_order po
                JOIN res_company c ON c.id = po.company_id
                WHERE po.state IN ('paid', 'done', 'invoiced')
            )
        """ % self._table)
