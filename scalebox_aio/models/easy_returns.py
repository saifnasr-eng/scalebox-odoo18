# -*- coding: utf-8 -*-
# Part of Scalebox All-in-One ERP.
# Copyright (C) 2026 Scalebox For Digital Services. All Rights Reserved.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class ScaleboxReturnMixin(models.AbstractModel):
    """Shared logic for sales and purchase returns."""

    _name = 'scalebox.return.mixin'
    _description = 'Scalebox - Returns Base'

    def _check_manager(self):
        if not self.env.user.has_group('scalebox_aio.group_scalebox_manager'):
            raise UserError(_('This action is restricted to managers only.'))

    def _return_stock(self, pickings, qty_by_product):
        """Creates and validates a stock return via the official Odoo wizard.

        :param pickings: original validated stock pickings
        :param qty_by_product: dict {product: quantity} to be returned
        :return: recordset of validated return pickings
        """
        Wizard = self.env['stock.return.picking']
        remaining = dict(qty_by_product)
        return_pickings = self.env['stock.picking']
        precision = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')

        for picking in pickings.filtered(lambda p: p.state == 'done'):
            if all(float_is_zero(q, precision_digits=precision)
                   for q in remaining.values()):
                break
            wizard = Wizard.create({'picking_id': picking.id})
            has_qty = False
            for wline in wizard.product_return_moves:
                product = wline.product_id
                take = min(remaining.get(product, 0.0), wline.move_quantity)
                if float_compare(take, 0.0, precision_digits=precision) > 0:
                    wline.quantity = take
                    remaining[product] = remaining.get(product, 0.0) - take
                    has_qty = True
                else:
                    wline.quantity = 0.0
            if not has_qty:
                continue
            new_picking = wizard._create_return()
            for move in new_picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            new_picking.with_context(skip_backorder=True).button_validate()
            return_pickings |= new_picking

        leftover = {
            p: q for p, q in remaining.items()
            if p.type != 'service'
            and float_compare(q, 0.0, precision_digits=precision) > 0
        }
        if leftover:
            raise UserError(_(
                'Not enough delivered/received quantities to return: %s',
                ', '.join('%s (%.2f)' % (p.display_name, q)
                          for p, q in leftover.items())))
        return return_pickings


class ScaleboxEasySaleReturn(models.Model):
    """Sales return: posted credit note + validated stock return + optional cash refund."""

    _name = 'scalebox.easy.sale.return'
    _description = 'Scalebox - Sales Return'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'scalebox.return.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Reference', default=lambda self: _('New'),
        copy=False, readonly=True, tracking=True)
    origin_id = fields.Many2one(
        'scalebox.easy.sale', string='Original Sale Operation', required=True,
        domain="[('state', '=', 'done')]", check_company=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency', readonly=True)
    partner_id = fields.Many2one(
        related='origin_id.partner_id', string='Customer', store=True)
    date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today)
    user_id = fields.Many2one(
        'res.users', string='Responsible', required=True,
        default=lambda self: self.env.user)
    reason = fields.Char(string='Return Reason')
    line_ids = fields.One2many(
        'scalebox.easy.sale.return.line', 'return_id', string='Lines',
        copy=True)
    amount_untaxed = fields.Monetary(
        string='Untaxed Total', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(
        string='Total', compute='_compute_amounts', store=True,
        tracking=True)
    refund_now = fields.Boolean(
        string='Instant Refund', default=False,
        help='On confirmation, a payment for the credit note amount is registered.')
    payment_journal_id = fields.Many2one(
        'account.journal', string='Refund Method', check_company=True,
        domain="[('type', 'in', ('bank', 'cash'))]")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Confirmed'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)
    refund_id = fields.Many2one(
        'account.move', string='Credit Note', readonly=True, copy=False)
    picking_ids = fields.Many2many(
        'stock.picking', string='Stock Returns', readonly=True, copy=False)

    @api.depends('line_ids.price_subtotal', 'line_ids.price_total')
    def _compute_amounts(self):
        for rec in self:
            rec.amount_untaxed = sum(rec.line_ids.mapped('price_subtotal'))
            rec.amount_total = sum(rec.line_ids.mapped('price_total'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'scalebox.easy.sale.return') or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'done' for rec in self):
            raise UserError(_('Cannot delete a confirmed return. Cancel it first.'))
        return super().unlink()

    @api.onchange('origin_id')
    def _onchange_origin_id(self):
        """Auto-fill lines with remaining returnable quantities."""
        self.line_ids = [(5, 0, 0)]
        if not self.origin_id:
            return
        returned = self._get_returned_qty_map(self.origin_id)
        lines = []
        for ol in self.origin_id.line_ids:
            remaining = ol.quantity - returned.get(ol.product_id.id, 0.0)
            if remaining > 0:
                lines.append((0, 0, {
                    'product_id': ol.product_id.id,
                    'quantity': remaining,
                    'price_unit': ol.price_unit,
                }))
        self.line_ids = lines

    @api.model
    def _get_returned_qty_map(self, origin):
        """Total previously returned quantities per product of the original operation."""
        result = {}
        prior = self.search([('origin_id', '=', origin.id),
                             ('state', '=', 'done')])
        for line in prior.mapped('line_ids'):
            result[line.product_id.id] = \
                result.get(line.product_id.id, 0.0) + line.quantity
        return result

    def action_confirm(self):
        precision = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.line_ids:
                raise UserError(_('Add at least one line before confirming.'))
            if rec.refund_now and not rec.payment_journal_id:
                raise UserError(_('Select a refund method or disable instant refund.'))

            # Check: returns must not exceed sold quantity
            returned = rec._get_returned_qty_map(rec.origin_id)
            sold = {}
            for ol in rec.origin_id.line_ids:
                sold[ol.product_id.id] = sold.get(ol.product_id.id, 0.0) + ol.quantity
            for line in rec.line_ids:
                total = returned.get(line.product_id.id, 0.0) + line.quantity
                if float_compare(total, sold.get(line.product_id.id, 0.0),
                                 precision_digits=precision) > 0:
                    raise UserError(_(
                        'Returned quantity of %s exceeds the sold quantity of the original operation.',
                        line.product_id.display_name))

            # 1) Credit note
            refund = self.env['account.move'].create({
                'move_type': 'out_refund',
                'partner_id': rec.partner_id.id,
                'invoice_date': rec.date,
                'company_id': rec.company_id.id,
                'ref': '%s - %s' % (rec.name, rec.reason or rec.origin_id.name),
                'reversed_entry_id': rec.origin_id.invoice_id.id or False,
                'invoice_line_ids': [(0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                }) for line in rec.line_ids],
            })
            refund.action_post()
            rec.refund_id = refund

            # 2) Stock return
            qty_by_product = {}
            for line in rec.line_ids:
                qty_by_product[line.product_id] = \
                    qty_by_product.get(line.product_id, 0.0) + line.quantity
            pickings = rec.origin_id.picking_ids.filtered(
                lambda p: p.picking_type_code == 'outgoing')
            return_pickings = rec._return_stock(pickings, qty_by_product)
            rec.picking_ids = [(6, 0, return_pickings.ids)]

            # 3) Refund
            if rec.refund_now:
                self.env['account.payment.register'].with_context(
                    active_model='account.move',
                    active_ids=refund.ids,
                ).create({
                    'journal_id': rec.payment_journal_id.id,
                    'payment_date': rec.date,
                }).action_create_payments()

            rec.state = 'done'
            rec.message_post(body=_(
                'Return confirmed: Credit note %s', refund.name))
        return True

    def action_cancel(self):
        self._check_manager()
        for rec in self:
            if rec.refund_id and rec.refund_id.state == 'posted':
                if rec.refund_id.payment_state in ('paid', 'in_payment', 'partial'):
                    raise UserError(_(
                        'Credit note %s is paid. Cancel the payment first.',
                        rec.refund_id.name))
                rec.refund_id.button_draft()
                rec.refund_id.button_cancel()
            rec.state = 'cancel'
        return True

    def action_draft(self):
        self._check_manager()
        for rec in self:
            if rec.state != 'cancel':
                raise UserError(_('Only cancelled returns can be reset to draft.'))
            rec.state = 'draft'
        return True

    def action_view_refund(self):
        self.ensure_one()
        if not self.refund_id:
            raise UserError(_('No credit note yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credit Note'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.refund_id.id,
        }


class ScaleboxEasySaleReturnLine(models.Model):
    _name = 'scalebox.easy.sale.return.line'
    _description = 'Scalebox - Sales Return Line'

    return_id = fields.Many2one(
        'scalebox.easy.sale.return', string='Return', required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(related='return_id.company_id', store=True)
    currency_id = fields.Many2one(related='return_id.currency_id')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True)
    quantity = fields.Float(
        string='Quantity', default=1.0, required=True,
        digits='Product Unit of Measure')
    price_unit = fields.Float(
        string='Unit Price', required=True, digits='Product Price')
    tax_ids = fields.Many2many(
        'account.tax', string='Taxes',
        compute='_compute_tax_ids', store=True, readonly=False,
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]")
    price_subtotal = fields.Monetary(
        string='Untaxed', compute='_compute_price', store=True)
    price_total = fields.Monetary(
        string='Total', compute='_compute_price', store=True)

    @api.depends('product_id', 'company_id')
    def _compute_tax_ids(self):
        for line in self:
            company = line.company_id or self.env.company
            line.tax_ids = line.product_id.taxes_id.filtered(
                lambda t: t.company_id == company)

    @api.depends('quantity', 'price_unit', 'tax_ids')
    def _compute_price(self):
        for line in self:
            base = line.quantity * line.price_unit
            if line.tax_ids:
                taxes = line.tax_ids.compute_all(
                    line.price_unit, currency=line.currency_id,
                    quantity=line.quantity, product=line.product_id,
                    partner=line.return_id.partner_id)
                line.price_subtotal = taxes['total_excluded']
                line.price_total = taxes['total_included']
            else:
                line.price_subtotal = base
                line.price_total = base


class ScaleboxEasyPurchaseReturn(models.Model):
    """Purchase return: posted debit note + validated stock return + optional refund."""

    _name = 'scalebox.easy.purchase.return'
    _description = 'Scalebox - Purchase Return'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'scalebox.return.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Reference', default=lambda self: _('New'),
        copy=False, readonly=True, tracking=True)
    origin_id = fields.Many2one(
        'scalebox.easy.purchase', string='Original Purchase Operation', required=True,
        domain="[('state', '=', 'done')]", check_company=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency', readonly=True)
    partner_id = fields.Many2one(
        related='origin_id.partner_id', string='Vendor', store=True)
    date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today)
    user_id = fields.Many2one(
        'res.users', string='Responsible', required=True,
        default=lambda self: self.env.user)
    reason = fields.Char(string='Return Reason')
    line_ids = fields.One2many(
        'scalebox.easy.purchase.return.line', 'return_id', string='Lines',
        copy=True)
    amount_untaxed = fields.Monetary(
        string='Untaxed Total', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(
        string='Total', compute='_compute_amounts', store=True,
        tracking=True)
    refund_now = fields.Boolean(
        string='Instant Refund', default=False,
        help='On confirmation, a receipt for the debit note amount is registered.')
    payment_journal_id = fields.Many2one(
        'account.journal', string='Refund Method', check_company=True,
        domain="[('type', 'in', ('bank', 'cash'))]")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Confirmed'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)
    refund_id = fields.Many2one(
        'account.move', string='Debit Note', readonly=True, copy=False)
    picking_ids = fields.Many2many(
        'stock.picking', string='Stock Returns', readonly=True, copy=False)

    @api.depends('line_ids.price_subtotal', 'line_ids.price_total')
    def _compute_amounts(self):
        for rec in self:
            rec.amount_untaxed = sum(rec.line_ids.mapped('price_subtotal'))
            rec.amount_total = sum(rec.line_ids.mapped('price_total'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'scalebox.easy.purchase.return') or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'done' for rec in self):
            raise UserError(_('Cannot delete a confirmed return. Cancel it first.'))
        return super().unlink()

    @api.onchange('origin_id')
    def _onchange_origin_id(self):
        self.line_ids = [(5, 0, 0)]
        if not self.origin_id:
            return
        returned = self._get_returned_qty_map(self.origin_id)
        lines = []
        for ol in self.origin_id.line_ids:
            remaining = ol.quantity - returned.get(ol.product_id.id, 0.0)
            if remaining > 0:
                lines.append((0, 0, {
                    'product_id': ol.product_id.id,
                    'quantity': remaining,
                    'price_unit': ol.price_unit,
                }))
        self.line_ids = lines

    @api.model
    def _get_returned_qty_map(self, origin):
        result = {}
        prior = self.search([('origin_id', '=', origin.id),
                             ('state', '=', 'done')])
        for line in prior.mapped('line_ids'):
            result[line.product_id.id] = \
                result.get(line.product_id.id, 0.0) + line.quantity
        return result

    def action_confirm(self):
        precision = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.line_ids:
                raise UserError(_('Add at least one line before confirming.'))
            if rec.refund_now and not rec.payment_journal_id:
                raise UserError(_('Select a refund method or disable instant refund.'))

            returned = rec._get_returned_qty_map(rec.origin_id)
            bought = {}
            for ol in rec.origin_id.line_ids:
                bought[ol.product_id.id] = bought.get(ol.product_id.id, 0.0) + ol.quantity
            for line in rec.line_ids:
                total = returned.get(line.product_id.id, 0.0) + line.quantity
                if float_compare(total, bought.get(line.product_id.id, 0.0),
                                 precision_digits=precision) > 0:
                    raise UserError(_(
                        'Returned quantity of %s exceeds the purchased quantity of the original operation.',
                        line.product_id.display_name))

            # 1) Debit note
            refund = self.env['account.move'].create({
                'move_type': 'in_refund',
                'partner_id': rec.partner_id.id,
                'invoice_date': rec.date,
                'company_id': rec.company_id.id,
                'ref': '%s - %s' % (rec.name, rec.reason or rec.origin_id.name),
                'reversed_entry_id': rec.origin_id.invoice_id.id or False,
                'invoice_line_ids': [(0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                }) for line in rec.line_ids],
            })
            refund.action_post()
            rec.refund_id = refund

            # 2) Stock return
            qty_by_product = {}
            for line in rec.line_ids:
                qty_by_product[line.product_id] = \
                    qty_by_product.get(line.product_id, 0.0) + line.quantity
            pickings = rec.origin_id.picking_ids.filtered(
                lambda p: p.picking_type_code == 'incoming')
            return_pickings = rec._return_stock(pickings, qty_by_product)
            rec.picking_ids = [(6, 0, return_pickings.ids)]

            # 3) Refund
            if rec.refund_now:
                self.env['account.payment.register'].with_context(
                    active_model='account.move',
                    active_ids=refund.ids,
                ).create({
                    'journal_id': rec.payment_journal_id.id,
                    'payment_date': rec.date,
                }).action_create_payments()

            rec.state = 'done'
            rec.message_post(body=_(
                'Return confirmed: Debit note %s', refund.name))
        return True

    def action_cancel(self):
        self._check_manager()
        for rec in self:
            if rec.refund_id and rec.refund_id.state == 'posted':
                if rec.refund_id.payment_state in ('paid', 'in_payment', 'partial'):
                    raise UserError(_(
                        'Debit note %s is paid. Cancel the payment first.',
                        rec.refund_id.name))
                rec.refund_id.button_draft()
                rec.refund_id.button_cancel()
            rec.state = 'cancel'
        return True

    def action_draft(self):
        self._check_manager()
        for rec in self:
            if rec.state != 'cancel':
                raise UserError(_('Only cancelled returns can be reset to draft.'))
            rec.state = 'draft'
        return True

    def action_view_refund(self):
        self.ensure_one()
        if not self.refund_id:
            raise UserError(_('No debit note yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Debit Note'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.refund_id.id,
        }


class ScaleboxEasyPurchaseReturnLine(models.Model):
    _name = 'scalebox.easy.purchase.return.line'
    _description = 'Scalebox - Purchase Return Line'

    return_id = fields.Many2one(
        'scalebox.easy.purchase.return', string='Return', required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(related='return_id.company_id', store=True)
    currency_id = fields.Many2one(related='return_id.currency_id')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True)
    quantity = fields.Float(
        string='Quantity', default=1.0, required=True,
        digits='Product Unit of Measure')
    price_unit = fields.Float(
        string='Unit Price', required=True, digits='Product Price')
    tax_ids = fields.Many2many(
        'account.tax', string='Taxes',
        compute='_compute_tax_ids', store=True, readonly=False,
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]")
    price_subtotal = fields.Monetary(
        string='Untaxed', compute='_compute_price', store=True)
    price_total = fields.Monetary(
        string='Total', compute='_compute_price', store=True)

    @api.depends('product_id', 'company_id')
    def _compute_tax_ids(self):
        for line in self:
            company = line.company_id or self.env.company
            line.tax_ids = line.product_id.supplier_taxes_id.filtered(
                lambda t: t.company_id == company)

    @api.depends('quantity', 'price_unit', 'tax_ids')
    def _compute_price(self):
        for line in self:
            base = line.quantity * line.price_unit
            if line.tax_ids:
                taxes = line.tax_ids.compute_all(
                    line.price_unit, currency=line.currency_id,
                    quantity=line.quantity, product=line.product_id,
                    partner=line.return_id.partner_id)
                line.price_subtotal = taxes['total_excluded']
                line.price_total = taxes['total_included']
            else:
                line.price_subtotal = base
                line.price_total = base
