# Scalebox All-in-One ERP (Odoo 18 Community)

**© 2026 Scalebox For Digital Services — جميع الحقوق محفوظة (License: OPL-1)**

طبقة مبسّطة فوق أودو 18 كوميونيتي للشركات الصغيرة (حتى 10 مستخدمين):
شاشة واحدة لكل عملية، والمحرك تحتها هو محرك أودو القياسي بالكامل
(sale.order / purchase.order / stock.picking / account.move / res.partner / product.product).

## التنصيب
1. انسخ مجلد `scalebox_aio` إلى مسار الـ addons (مثال: `/mnt/extra-addons` في دوكر).
2. أعد تشغيل أودو ثم حدّث قائمة التطبيقات (Apps → Update Apps List).
3. ابحث عن "Scalebox" ونصّب الموديول.

## المتطلبات
- Odoo 18 Community
- التطبيقات: Sales, Purchase, Inventory, Invoicing (تتنصّب تلقائياً كاعتماديات)

## ماذا يحدث عند "تأكيد البيع"؟
1. إنشاء وتأكيد أمر بيع (sale.order)
2. تسليم المخزون وتأكيد حركة الإخراج (stock.picking)
3. إنشاء وترحيل فاتورة العميل (account.move)
4. (اختياري) تسجيل سند قبض فوري (account.payment)

نفس الدورة معكوسة في "تأكيد الشراء".

## ملاحظات تشغيلية
- المنتجات المخزنية تُسلَّم بالكمية المطلوبة مباشرة (skip backorder).
- الضرائب تُسحب تلقائياً من إعدادات المنتج (شامل ضريبة القيمة المضافة).
- كشوف الحسابات تُقرأ مباشرة من قيود أودو الرسمية (account.move.line) — لا تكرار للبيانات.
