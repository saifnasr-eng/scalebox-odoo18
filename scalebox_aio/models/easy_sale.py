# -*- coding: utf-8 -*-
# Part of Scalebox All-in-One ERP.
# Copyright (C) 2026 Scalebox For Digital Services. All Rights Reserved.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ScaleboxEasySale(models.Model):
    """Easy Sale screen: creates the sale order, delivers stock, issues the invoice,
    and registers the payment in one step, fully using the standard Odoo engine."""

    _name = 'scalebox.easy.sale'
    _description = 'Scalebox - Easy Sale'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Reference', default=lambda self: _('New'),
        copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency', readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, tracking=True,
        domain="[('company_id', 'in', (False, company_id))]")
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse', required=True,
        check_company=True,
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1))
    date = fields.Date(
        string='Date', required=True,
        default=fields.Date.context_today)
    user_id = fields.Many2one(
        'res.users', string='Responsible', required=True,
        default=lambda self: self.env.user)
    line_ids = fields.One2many(
        'scalebox.easy.sale.line', 'easy_sale_id', string='Lines',
        copy=True)
    amount_untaxed = fields.Monetary(
        string='Untaxed Total', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(
        string='Total', compute='_compute_amounts', store=True,
        tracking=True)
    pay_now = fields.Boolean(
        string='Instant Collection', default=True,
        help='On confirmation, a receipt for the full invoice amount is registered automatically.')
    payment_journal_id = fields.Many2one(
        'account.journal', string='Collection Method',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Confirmed'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)
    sale_order_id = fields.Many2one(
        'sale.order', string='Sale Order', readonly=True, copy=False)
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', readonly=True, copy=False)
    picking_ids = fields.Many2many(
        'stock.picking', string='Stock Operations', readonly=True, copy=False)
    note = fields.Text(string='Notes')

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('line_ids.price_subtotal', 'line_ids.price_total')
    def _compute_amounts(self):
        for rec in self:
            rec.amount_untaxed = sum(rec.line_ids.mapped('price_subtotal'))
            rec.amount_total = sum(rec.line_ids.mapped('price_total'))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'scalebox.easy.sale') or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'done' for rec in self):
            raise UserError(_('Cannot delete a confirmed sale. Cancel it first.'))
        return super().unlink()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Runs the full cycle: sale order -> delivery -> invoice -> collection."""
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.line_ids:
                raise UserError(_('Add at least one line before confirming.'))
            if rec.pay_now and not rec.payment_journal_id:
                raise UserError(_('Select a collection method (cash or bank) or disable instant collection.'))

            # Block negative stock selling (unless the user has the bypass right)
            if not self.env.user.has_group('scalebox_aio.group_scalebox_negative'):
                needed = {}
                for line in rec.line_ids.filtered(
                        lambda l: l.product_id.is_storable):
                    needed[line.product_id] = \
                        needed.get(line.product_id, 0.0) + line.quantity
                shortages = []
                for product, qty in needed.items():
                    available = product.with_context(
                        warehouse_id=rec.warehouse_id.id).qty_available
                    if available < qty:
                        shortages.append('%s (Available: %.2f / Required: %.2f)' % (
                            product.display_name, available, qty))
                if shortages:
                    raise UserError(_(
                        'Negative stock selling is not allowed. The following products have insufficient stock in warehouse %s:\n%s',
                        rec.warehouse_id.name, '\n'.join(shortages)))

            # 1) Sale order
            order = self.env['sale.order'].create(rec._prepare_sale_order_vals())
            order.action_confirm()
            rec.sale_order_id = order

            # 2) Stock delivery
            pickings = order.picking_ids.filtered(
                lambda p: p.state not in ('done', 'cancel'))
            for picking in pickings:
                picking.action_assign()
                for move in picking.move_ids:
                    move.quantity = move.product_uom_qty
                    move.picked = True
                picking.with_context(skip_backorder=True).button_validate()
            rec.picking_ids = [(6, 0, order.picking_ids.ids)]

            # 3) Invoice
            invoice = order._create_invoices()
            invoice.invoice_date = rec.date
            invoice.action_post()
            rec.invoice_id = invoice

            # 4) Instant collection
            if rec.pay_now:
                self.env['account.payment.register'].with_context(
                    active_model='account.move',
                    active_ids=invoice.ids,
                ).create({
                    'journal_id': rec.payment_journal_id.id,
                    'payment_date': rec.date,
                }).action_create_payments()

            rec.state = 'done'
            rec.message_post(body=_(
                'Operation confirmed: Sale order %s | Invoice %s',
                order.name, invoice.name))
        return True

    def action_cancel(self):
        if not self.env.user.has_group('scalebox_aio.group_scalebox_manager'):
            raise UserError(_('Cancelling operations is restricted to managers only.'))
        for rec in self:
            if rec.invoice_id and rec.invoice_id.state == 'posted':
                if rec.invoice_id.payment_state in ('paid', 'in_payment', 'partial'):
                    raise UserError(_(
                        'Invoice %s is fully or partially paid. Cancel the payment from '
                        'the Accounting screen first.', rec.invoice_id.name))
                rec.invoice_id.button_draft()
                rec.invoice_id.button_cancel()
            if rec.sale_order_id and rec.sale_order_id.state != 'cancel':
                rec.sale_order_id.with_context(disable_cancel_warning=True)._action_cancel()
            rec.state = 'cancel'
        return True

    def action_draft(self):
        if not self.env.user.has_group('scalebox_aio.group_scalebox_manager'):
            raise UserError(_('This action is restricted to managers only.'))
        for rec in self:
            if rec.state != 'cancel':
                raise UserError(_('Only cancelled operations can be reset to draft.'))
            rec.state = 'draft'
        return True

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
        }

    def action_view_partner_ledger(self):
        """Partner statement from official Odoo journal items."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Statement: %s', self.partner_id.display_name),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.partner_id.id),
                ('account_id.account_type', 'in',
                 ('asset_receivable', 'liability_payable')),
                ('parent_state', '=', 'posted'),
            ],
            'context': {'create': False},
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _prepare_sale_order_vals(self):
        self.ensure_one()
        return {
            'partner_id': self.partner_id.id,
            'date_order': fields.Datetime.to_datetime(self.date),
            'user_id': self.user_id.id,
            'company_id': self.company_id.id,
            'warehouse_id': self.warehouse_id.id,
            'origin': self.name,
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'price_unit': line.price_unit,
                'discount': line.discount,
            }) for line in self.line_ids],
        }


class ScaleboxEasySaleLine(models.Model):
    _name = 'scalebox.easy.sale.line'
    _description = 'Scalebox - Easy Sale Line'

    easy_sale_id = fields.Many2one(
        'scalebox.easy.sale', string='Sale Operation', required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='easy_sale_id.company_id', store=True)
    currency_id = fields.Many2one(
        related='easy_sale_id.currency_id')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain="[('sale_ok', '=', True)]")
    quantity = fields.Float(
        string='Quantity', default=1.0, required=True,
        digits='Product Unit of Measure')
    price_unit = fields.Float(
        string='Unit Price', required=True, digits='Product Price')
    discount = fields.Float(string='Discount %', digits='Discount')
    qty_available = fields.Float(
        string='Available in Warehouse', compute='_compute_qty_available',
        digits='Product Unit of Measure',
        help='Available quantity of the product in the selected warehouse at the time of the operation.')
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

    @api.depends('product_id', 'easy_sale_id.warehouse_id')
    def _compute_qty_available(self):
        for line in self:
            if line.product_id and line.product_id.is_storable:
                wh = line.easy_sale_id.warehouse_id
                product = line.product_id.with_context(
                    warehouse_id=wh.id) if wh else line.product_id
                line.qty_available = product.qty_available
            else:
                line.qty_available = 0.0

    @api.onchange('product_id', 'quantity')
    def _onchange_product_id(self):
        if self.product_id:
            partner = self.easy_sale_id.partner_id
            pricelist = partner.property_product_pricelist if partner else False
            if pricelist:
                self.price_unit = pricelist._get_product_price(
                    self.product_id, self.quantity or 1.0)
            elif not self.price_unit:
                self.price_unit = self.product_id.list_price

    @api.depends('quantity', 'price_unit', 'discount', 'tax_ids')
    def _compute_price(self):
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            base = line.quantity * price
            if line.tax_ids:
                taxes = line.tax_ids.compute_all(
                    price,
                    currency=line.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=line.easy_sale_id.partner_id,
                )
                line.price_subtotal = taxes['total_excluded']
                line.price_total = taxes['total_included']
            else:
                line.price_subtotal = base
                line.price_total = base
