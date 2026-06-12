# -*- coding: utf-8 -*-
# Part of Scalebox All-in-One ERP.
# Copyright (C) 2026 Scalebox For Digital Services. All Rights Reserved.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ScaleboxDetailReport(models.TransientModel):
    """Printable detailed report for sales or purchases including returns."""

    _name = 'scalebox.detail.report'
    _description = 'Scalebox - Detailed Report'

    report_type = fields.Selection([
        ('sale', 'Sales'),
        ('purchase', 'Purchases'),
    ], string='Report', required=True, default='sale')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', readonly=True)
    date_from = fields.Date(
        string='From Date', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string='To Date', required=True,
        default=fields.Date.context_today)
    partner_id = fields.Many2one(
        'res.partner', string='Customer / Vendor (Optional)')
    line_ids = fields.One2many(
        'scalebox.detail.report.line', 'wizard_id', string='Lines')
    gross_total = fields.Monetary(string='Total', readonly=True)
    returns_total = fields.Monetary(string='Total Returns', readonly=True)
    net_total = fields.Monetary(string='Net', readonly=True)

    def _doc_domain(self):
        self.ensure_one()
        domain = [
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        return domain

    def action_generate(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('Start date must be before end date.'))
        self.line_ids.unlink()
        if self.report_type == 'sale':
            Doc = self.env['scalebox.easy.sale']
            Ret = self.env['scalebox.easy.sale.return']
        else:
            Doc = self.env['scalebox.easy.purchase']
            Ret = self.env['scalebox.easy.purchase.return']

        vals_list = []
        seq = 0
        gross = 0.0
        for doc in Doc.search(self._doc_domain(), order='date, id'):
            seq += 10
            gross += doc.amount_total
            vals_list.append({
                'wizard_id': self.id,
                'sequence': seq,
                'date': doc.date,
                'name': doc.name,
                'partner_id': doc.partner_id.id,
                'doc_kind': 'doc',
                'amount_untaxed': doc.amount_untaxed,
                'amount_tax': doc.amount_total - doc.amount_untaxed,
                'amount_total': doc.amount_total,
            })
        returns = 0.0
        for ret in Ret.search(self._doc_domain(), order='date, id'):
            seq += 10
            returns += ret.amount_total
            vals_list.append({
                'wizard_id': self.id,
                'sequence': seq,
                'date': ret.date,
                'name': ret.name,
                'partner_id': ret.partner_id.id,
                'doc_kind': 'return',
                'amount_untaxed': -ret.amount_untaxed,
                'amount_tax': -(ret.amount_total - ret.amount_untaxed),
                'amount_total': -ret.amount_total,
            })
        self.env['scalebox.detail.report.line'].create(vals_list)
        self.gross_total = gross
        self.returns_total = returns
        self.net_total = gross - returns
        return {
            'type': 'ir.actions.act_window',
            'name': _('Detailed Report'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_print(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_generate()
        return self.env.ref(
            'scalebox_aio.action_report_detail').report_action(self)


class ScaleboxDetailReportLine(models.TransientModel):
    _name = 'scalebox.detail.report.line'
    _description = 'Scalebox - Detailed Report Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'scalebox.detail.report', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    date = fields.Date(string='Date', readonly=True)
    name = fields.Char(string='Reference', readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Customer / Vendor', readonly=True)
    doc_kind = fields.Selection([
        ('doc', 'Operation'),
        ('return', 'Return'),
    ], string='Type', readonly=True)
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    amount_untaxed = fields.Monetary(string='Untaxed', readonly=True)
    amount_tax = fields.Monetary(string='Tax', readonly=True)
    amount_total = fields.Monetary(string='Total', readonly=True)
