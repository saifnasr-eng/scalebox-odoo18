# -*- coding: utf-8 -*-
# Part of Scalebox All-in-One ERP.
# Copyright (C) 2026 Scalebox For Digital Services. All Rights Reserved.
{
    'name': 'Scalebox All-in-One ERP',
    'version': '18.0.6.0.1',
    'price': 99.00,
    'currency': 'USD',
    'category': 'Accounting/Accounting',
    'summary': 'Simple all-in-one ERP: sales, purchases, inventory, accounting, POS and reports in one app',
    'description': """
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
        'hr_expense',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/scalebox_menu.xml',
        'views/sale_views.xml',
        'views/purchase_views.xml',
        'views/stock_views.xml',
        'views/account_views.xml',
        'views/expense_views.xml',
        'views/report_views.xml',
        'views/dashboard_views.xml',
        'data/expense_type_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'scalebox_aio/static/src/js/dashboard.js',
            'scalebox_aio/static/src/css/dashboard.css',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
