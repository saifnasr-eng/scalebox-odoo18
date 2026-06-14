# -*- coding: utf-8 -*-
# Part of Scalebox All-in-One ERP.
# Copyright (C) 2026 Scalebox For Digital Services. All Rights Reserved.
{
    'name': 'Scalebox All-in-One ERP',
    'version': '18.0.6.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Simple all-in-one ERP: sales, purchases, inventory, accounting, POS and reports in one app',
    'description': """
    'website': 'https://scalebox.scbox.pro/',
Scalebox All-in-One ERP
=======================
A simplified layer on top of Odoo 18 Community for small businesses (up to 10 users).

- Easy Sale screen: sale order + stock delivery + invoice + payment in one step.
- Easy Purchase screen: purchase order + stock receipt + vendor bill + payment in one step.
- Sales and purchase returns with automatic credit/debit notes and stock returns.
- Expenses with configurable types, automatic journal entries and printable vouchers.
- Embedded official Point of Sale, loyalty programs and landed costs.
- Live KPI dashboard, financial reports (BS / P&L / Cash Flow) and printable reports.
- Two-level access rights (User / Manager) and negative-stock selling control.
- Fully bilingual (English / Arabic).

Built entirely on standard Odoo tables (res.partner / product.product / res.users /
sale.order / purchase.order / stock.picking / account.move) with no data duplication,
keeping all accounting and inventory postings valid and compatible with standard reports.
""",
    'author': 'Scalebox For Digital Services',
    'maintainer': 'Scalebox For Digital Services',
    'website': 'https://scalebox.scbox.pro',
    'license': 'OPL-1',
    'depends': [
        'base',
        'mail',
        'product',
        'sale_management',
        'purchase',
        'stock',
        'account',
        'point_of_sale',
        'loyalty',
        'sale_loyalty',
        'pos_loyalty',
        'stock_landed_costs',
    ],
    'data': [
        'security/scalebox_security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'views/easy_sale_views.xml',
        'views/easy_purchase_views.xml',
        'views/expense_views.xml',
        'views/return_views.xml',
        'views/financial_report_views.xml',
        'views/wizard_report_views.xml',
        'views/operations_views.xml',
        'views/report_views.xml',
        'report/expense_receipt_report.xml',
        'report/printable_reports.xml',
        'views/dashboard_views.xml',
        'views/menus.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
    'price': 99.00,
    'currency': 'USD',
}
