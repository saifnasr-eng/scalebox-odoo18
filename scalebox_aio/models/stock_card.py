# -*- coding: utf-8 -*-
# Part of Scalebox All-in-One ERP.
# Copyright (C) 2026 Scalebox For Digital Services. All Rights Reserved.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ScaleboxStockCard(models.TransientModel):
    """Product stock card: in / out / running balance, with PDF printing."""

    _name = 'scalebox.stock.card'
    _description = 'Scalebox - Product Stock Card'

    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain="[('type', '=', 'consu')]")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    date_from = fields.Date(
        string='From Date', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string='To Date', required=True,
        default=fields.Date.context_today)
    opening_qty = fields.Float(
        string='Opening Balance', readonly=True,
        digits='Product Unit of Measure')
    closing_qty = fields.Float(
        string='Closing Balance', readonly=True,
        digits='Product Unit of Measure')
    total_in = fields.Float(
        string='Total In', readonly=True,
        digits='Product Unit of Measure')
    total_out = fields.Float(
        string='Total Out', readonly=True,
        digits='Product Unit of Measure')
    line_ids = fields.One2many(
        'scalebox.stock.card.line', 'wizard_id', string='Moves')

    def _move_domain(self):
        self.ensure_one()
        return [
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
            ('product_id', '=', self.product_id.id),
        ]

    @api.model
    def _move_direction(self, move):
        """+qty for incoming, -qty for outgoing, 0 for internal transfers."""
        src_internal = move.location_id.usage == 'internal'
        dest_internal = move.location_dest_id.usage == 'internal'
        if dest_internal and not src_internal:
            return move.quantity
        if src_internal and not dest_internal:
            return -move.quantity
        return 0.0

    def action_generate(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('Start date must be before end date.'))
        self.line_ids.unlink()
        Move = self.env['stock.move']

        # Opening balance: all moves before the start date
        opening = 0.0
        prior_moves = Move.search(
            self._move_domain() + [('date', '<', fields.Datetime.to_datetime(self.date_from))])
        for move in prior_moves:
            opening += self._move_direction(move)

        # Period moves in chronological order
        period_moves = Move.search(
            self._move_domain() + [
                ('date', '>=', fields.Datetime.to_datetime(self.date_from)),
                ('date', '<', fields.Datetime.add(
                    fields.Datetime.to_datetime(self.date_to), days=1)),
            ], order='date, id')

        balance = opening
        total_in = total_out = 0.0
        vals_list = []
        seq = 0
        for move in period_moves:
            qty = self._move_direction(move)
            if not qty:
                continue
            balance += qty
            if qty > 0:
                total_in += qty
            else:
                total_out += -qty
            seq += 10
            vals_list.append({
                'wizard_id': self.id,
                'sequence': seq,
                'date': move.date,
                'reference': move.reference or move.picking_id.name or '/',
                'partner_id': move.picking_id.partner_id.id or move.partner_id.id,
                'qty_in': qty if qty > 0 else 0.0,
                'qty_out': -qty if qty < 0 else 0.0,
                'balance': balance,
            })
        self.env['scalebox.stock.card.line'].create(vals_list)
        self.opening_qty = opening
        self.closing_qty = balance
        self.total_in = total_in
        self.total_out = total_out
        return {
            'type': 'ir.actions.act_window',
            'name': _('Product Stock Card'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_print(self):
        self.ensure_one()
        if not self.line_ids and not self.opening_qty:
            self.action_generate()
        return self.env.ref(
            'scalebox_aio.action_report_stock_card').report_action(self)


class ScaleboxStockCardLine(models.TransientModel):
    _name = 'scalebox.stock.card.line'
    _description = 'Scalebox - Stock Card Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'scalebox.stock.card', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    date = fields.Datetime(string='Date', readonly=True)
    reference = fields.Char(string='Reference', readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Customer / Vendor', readonly=True)
    qty_in = fields.Float(
        string='In', readonly=True, digits='Product Unit of Measure')
    qty_out = fields.Float(
        string='Out', readonly=True, digits='Product Unit of Measure')
    balance = fields.Float(
        string='Balance', readonly=True, digits='Product Unit of Measure')
