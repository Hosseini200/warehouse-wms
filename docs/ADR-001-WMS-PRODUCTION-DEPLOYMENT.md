# ADR-001: استقرار تولید سامانه مدیریت انبار

- وضعیت تصمیم: پذیرفته‌شده
- تاریخ: 2026-07-23
- سامانه: Warehouse Management System
- دامنه عمومی: https://wms.daroo100.com

---

## 1. زمینه و مسئله

سامانه مدیریت انبار شامل Backend مبتنی بر FastAPI، پایگاه داده PostgreSQL و Frontend مبتنی بر React/Vite/PWA است.

هدف این استقرار:

- اجرای پایدار سامانه روی Windows Server 2019
- عدم ایجاد اختلال در دامنه اصلی daroo100.com
- ارائه Frontend و API روی یک دامنه HTTPS
- اجرای خودکار Backend و PostgreSQL پس از Restart
- نگهداری بکاپ‌های قابل بازیابی
- محدودسازی سطح دسترسی شبکه و فایل‌های محرمانه
- فراهم‌کردن مسیر Rollback و تحویل عملیاتی

---

## 2. معماری نهایی

### Frontend

- فناوری: React + Vite + PWA
- نشانی عمومی:
  https://wms.daroo100.com/
- مسیر Build مرجع:
  C:\warehouse\builds\warehouse-pwa_20260722_114050
- مسیر انتشار IIS:
  C:\Inetpub\vhosts\daroo100.com\wms.daroo100.com
- API Base URL:
  /api
- JavaScript فعال:
  /assets/index-BE3zMFly.js

### Backend

- فناوری: FastAPI + Uvicorn + SQLAlchemy
- مسیر کد مرجع:
  C:\warehouse\backend\app
- محیط Python:
  C:\warehouse\backend\venv_new
- نشانی داخلی:
  http://127.0.0.1:8000
- Health Endpoint:
  /health
- Backend مستقیماً روی اینترنت منتشر نشده است.

### Reverse Proxy

- IIS 10
- Application Request Routing
- URL Rewrite
- درخواست‌های زیر:
  https://wms.daroo100.com/api/*
- به این نشانی منتقل می‌شوند:
  http://127.0.0.1:8000/*

پیشوند /api در IIS حذف می‌شود.

### Database

- PostgreSQL 16
- Database:
  warehouse_db_v2
- Application Role:
  warehouse_app
- Port:
  5432
- listen_addresses:
  localhost
- رابط‌های مجاز:
  127.0.0.1
  ::1
- روش احراز هویت:
  scram-sha-256

---

## 3. تصمیم‌های معماری

### تصمیم 1: استفاده از IIS به‌عنوان Web Server و Reverse Proxy

دلایل:

- IIS و Plesk از قبل روی سرور فعال بودند.
- نیاز به نصب Reverse Proxy جداگانه حذف شد.
- گواهی SSL و مدیریت دامنه با زیرساخت موجود هماهنگ شد.
- دامنه اصلی daroo100.com بدون تغییر باقی ماند.

گزینه‌های بررسی‌شده:

- Nginx
- اجرای مستقیم Uvicorn روی اینترنت
- انتشار Backend روی پورت مستقل

پیامد:

- IIS تنها نقطه عمومی ورود به WMS است.
- سلامت ARR و URL Rewrite برای دسترسی API ضروری است.

---

### تصمیم 2: محدودکردن Uvicorn به localhost

تنظیم نهایی:

127.0.0.1:8000

دلایل:

- Backend نباید مستقیماً از اینترنت قابل دسترسی باشد.
- HTTPS، Headerهای امنیتی و کنترل مسیرها در IIS انجام می‌شوند.
- سطح حمله کاهش می‌یابد.

پیامد:

- دسترسی عمومی Backend فقط از مسیر /api امکان‌پذیر است.
- در صورت خرابی IIS یا ARR، API عمومی در دسترس نخواهد بود.

---

### تصمیم 3: اجرای Backend با Scheduled Task و Supervisor

Task:

WarehouseBackend

حساب اجرا:

NT AUTHORITY\SYSTEM

حالت اجرا:

- Highest Privileges
- اجرای خودکار هنگام Boot
- اجرای Supervisor
- Restart خودکار Uvicorn در صورت Crash
- تأخیر Restart حدود 5 ثانیه

دلایل:

- اجرای پایدار بدون Login کاربر
- عدم نیاز به ابزار ثالث
- سازگاری مستقیم با Windows Server

گزینه جایگزین آینده:

- Windows Service
- NSSM
- سرویس‌مدیریت اختصاصی

پیامد:

- کد Supervisor بخشی از زیرساخت حیاتی است.
- LastTaskResult برابر 267009 در زمان اجرای دائمی Task، به معنی Running بودن Task است و خطا محسوب نمی‌شود.

---

### تصمیم 4: استفاده از محیط Python مستقل جدید

مسیر:

C:\warehouse\backend\venv_new

دلایل:

- حذف وابستگی‌های غیرضروری
- جلوگیری از استفاده از محیط قدیمی و آلوده
- تثبیت نسخه پکیج‌ها
- حذف Streamlit از محیط عملیاتی

پکیج‌های کلیدی:

- FastAPI 0.139.2
- Uvicorn 0.51.0
- SQLAlchemy 2.0.51
- Pydantic 2.13.4
- bcrypt 4.0.1
- psycopg2 2.9.12
- PyJWT 2.13.0

---

### تصمیم 5: انتشار PWA به‌صورت فایل‌های Static در IIS

دلایل:

- Frontend در Runtime به Node.js نیاز ندارد.
- سربار و سطح حمله کمتر می‌شود.
- انتشار سریع و قابل Rollback است.
- Service Worker و Manifest فعال باقی می‌مانند.

پیامد:

- پس از انتشار نسخه جدید، ممکن است Cache یا Service Worker مرورگر نیاز به Refresh یا حذف Site Data داشته باشد.
- فایل‌های Asset قدیمی باید هنگام انتشار پاک شوند.

---

### تصمیم 6: سیاست بکاپ چندلایه PostgreSQL

Scheduled Task:

WarehouseDatabaseBackup

زمان اجرا:

روزانه ساعت 02:00

فرمت:

PostgreSQL Custom Format

ویژگی‌ها:

- Compression Level 9
- اعتبارسنجی با pg_restore --list
- ثبت SHA-256
- ثبت Log

Retention:

- Daily: 30 روز
- Weekly: 12 هفته
- Monthly: 24 ماه

مسیرها:

C:\warehouse\backups\daily
C:\warehouse\backups\weekly
C:\warehouse\backups\monthly

اسکریپت:

C:\warehouse\scripts\backup_warehouse_db.ps1

لاگ:

C:\warehouse\logs\database_backup.log

دلایل:

- بازیابی سریع خطاهای روزمره
- نگهداری تاریخچه میان‌مدت و بلندمدت
- کاهش مصرف فضا با Compression و Tiering

ریسک باقی‌مانده:

تمام بکاپ‌ها فعلاً روی همان سرور قرار دارند.
برای تکمیل اصل 3-2-1، یک مقصد خارج از سرور با S3، SFTP یا NAS لازم است.

---

### تصمیم 7: محدودسازی PostgreSQL به localhost

تنظیم:

listen_addresses = 'localhost'

دلایل:

- فقط Backend همین سرور به PostgreSQL نیاز دارد.
- دسترسی مستقیم اینترنتی به Database ضرورتی ندارد.
- کاهش ریسک Brute-force و Exploit شبکه‌ای

نتیجه:

- 127.0.0.1:5432
- ::1:5432

پورت 5432 روی 0.0.0.0 یا :: منتشر نیست.

---

### تصمیم 8: محافظت از فایل .env

فایل فعال:

C:\warehouse\backend\.env

دسترسی نهایی:

- BUILTIN\Administrators: Full Control
- NT AUTHORITY\SYSTEM: Full Control

دسترسی BUILTIN\Users حذف شد.

نسخه‌های قدیمی دارای DATABASE_URL و SECRET_KEY از Release و Backupهای موقت حذف شدند.

مقادیر محرمانه نباید در مستندات، Logها یا Repository ذخیره شوند.

---

### تصمیم 9: تعویض رمز Admin و SECRET_KEY

اقدامات:

- رمز حساب Admin با bcrypt مجدداً Hash شد.
- SECRET_KEY جدید و تصادفی ایجاد شد.
- Backend Restart شد.
- Tokenهای JWT قدیمی منقضی شدند.
- ورود با رمز جدید عملیاتی آزمایش شد.

پیامد:

تعویض SECRET_KEY همه Sessionهای فعال قبلی را نامعتبر می‌کند.

---

### تصمیم 10: محدودسازی SQL Server مشترک سرور

SQL Server جزء وابستگی WMS نیست، اما روی همان سرور و پورت 1433 فعال بود.

مشاهده شد:

- Rule عمومی SQLServer default instance برای RemoteAddress=Any فعال بود.
- تلاش‌های متعدد Brute-force برای کاربران sa و نام‌های تصادفی در ERRORLOG ثبت شده بود.
- تلاش‌های مشاهده‌شده ناموفق بودند.

اقدام:

Rule عمومی غیرفعال شد.

Rule باقی‌مانده:

sqlport

IPهای مجاز:

- 5.202.68.2
- 5.201.185.67

پیامد:

سرویس‌هایی که از IPهای دیگر به SQL Server متصل می‌شدند، دیگر دسترسی ندارند.
کارفرما یا مدیر سرور باید ضرورت دو IP مجاز را تأیید کند.

---

## 4. تنظیمات امنیتی IIS

Headerهای فعال:

- Strict-Transport-Security
- X-Content-Type-Options
- X-Frame-Options
- Referrer-Policy
- Permissions-Policy
- Content-Security-Policy

HTTP به HTTPS منتقل می‌شود.

مسیرهای حساس و فایل‌های تنظیمات از دسترسی عمومی مسدود شده‌اند.

گواهی SSL:

- Subject: wms.daroo100.com
- Issuer: Let's Encrypt
- اعتبار مشاهده‌شده:
  2026-07-22 تا 2026-10-20

تمدید گواهی توسط Plesk/Let's Encrypt باید تحت پایش باقی بماند.

---

## 5. Log Management

Backend Log:

C:\warehouse\logs\backend.log

Rotation:

- حداکثر اندازه هر فایل: 10 MB
- تعداد Backup Logها: 20

دلایل:

- جلوگیری از رشد نامحدود Log
- نگهداری سابقه کافی برای عیب‌یابی

---

## 6. آزمون‌های انجام‌شده

### آزمون Health

موفق:

- Local Backend:
  http://127.0.0.1:8000/health
- Public API:
  https://wms.daroo100.com/api/health
- Public Frontend:
  https://wms.daroo100.com/

نتیجه:

HTTP 200 OK
{"status":"ok"}

### آزمون Crash Recovery

Uvicorn به‌صورت اجباری متوقف شد.

نتیجه:

- Supervisor آن را مجدداً اجرا کرد.
- زمان بازیابی مشاهده‌شده حدود 8.6 ثانیه بود.
- Health Endpoint دوباره پاسخ سالم داد.

### آزمون Restart کامل Windows Server

Windows Server Restart شد.

پس از Boot:

- PostgreSQL: Running / Automatic
- IIS W3SVC: Running / Automatic
- WarehouseBackend: Running
- Backend Port 8000: Listening
- سایت عمومی: 200 OK
- API عمومی: 200 OK
- Backup Task: Ready

### آزمون بکاپ

آخرین بکاپ آزمایشی:

C:\warehouse\backups\daily\warehouse_db_v2_daily_20260723_094057.backup

نتیجه:

- Task Result: 0
- Size: 48557 bytes
- pg_restore Validation: موفق
- SHA-256:
  55DE07B596059E7DD01279375DFB1EEDAB01E9E1E01435E18F64C0FC8A14311D

### آزمون سرتاسری حواله

Transfer ID:

1

مشخصات:

- Source Warehouse ID: 5
- Destination Warehouse ID: 6
- Product ID: 5
- Batch ID: 2
- Quantity: 1

مراحل موفق:

- ثبت حواله
- رزرو موجودی مبدأ
- تأیید خروج از مبدأ
- انتظار تأیید مقصد
- تأیید دریافت مقصد
- آزادسازی رزرو
- نهایی‌شدن وضعیت

وضعیت نهایی:

confirmed

موجودی نهایی:

- انبار مبدأ: 999
- انبار مقصد: 1
- Reserved Quantity هر دو انبار: 0

---

## 7. مشکل اصلاح‌شده Frontend

مشکل:

صفحه کارتابل حواله‌ها به‌جای ApprovalsPage، PlaceholderPage را نمایش می‌داد.

علت:

در App.jsx برای activePage برابر approvals، کامپوننت اشتباه Render شده بود.

اصلاح:

ApprovalsPage با user و onBack فعال شد.

فایل Build جدید:

index-BE3zMFly.js

نتیجه:

- انتخاب انبار
- مشاهده حواله
- تأیید مبدأ
- تأیید مقصد

همگی عملیاتی شدند.

---

## 8. مسیرهای عملیاتی مهم

Backend:

C:\warehouse\backend

Backend Application:

C:\warehouse\backend\app

Python Environment:

C:\warehouse\backend\venv_new

Frontend Build:

C:\warehouse\builds\warehouse-pwa_20260722_114050

IIS Document Root:

C:\Inetpub\vhosts\daroo100.com\wms.daroo100.com

Logs:

C:\warehouse\logs

Backups:

C:\warehouse\backups

Scripts:

C:\warehouse\scripts

Documentation:

C:\warehouse\docs

Site Rollback Backups:

C:\warehouse\site_backups

---

## 9. Rollback

### Frontend

نسخه قبلی سایت در مسیر زیر نگهداری شده است:

C:\warehouse\site_backups

برای Rollback باید محتوای Backup انتخاب‌شده به Document Root بازگردانده شود و web.config حفظ یا بازبینی شود.

### Backend

نسخه مرجع کد:

C:\warehouse\backend\app

کدهای Backup و نسخه‌های قبل از تغییر در مسیرهای مربوط به code_backups و فایل‌های .bak موجودند، به‌جز نسخه‌های قدیمی .env که عمداً به دلایل امنیتی حذف شدند.

### PostgreSQL Configuration

Backupهای postgresql.conf پیش از محدودسازی listen_addresses در Data Directory PostgreSQL موجودند.

### Database

بازیابی باید با pg_restore از یک Backup اعتبارسنجی‌شده انجام شود.

قبل از Restore کامل:

- Backup جدید از وضعیت جاری گرفته شود.
- Restore ترجیحاً ابتدا روی Database آزمایشی انجام شود.
- تعداد جداول و داده‌های کلیدی بررسی شوند.

---

## 10. ریسک‌ها و اقدامات باز

سند کامل:

C:\warehouse\docs\OPEN_RISKS.md

موارد اصلی:

1. نبود بکاپ خارج از سرور
2. بازبودن RDP برای اینترنت
3. سرویس‌های مشترک Plesk خارج از محدوده WMS
4. نیاز به تأیید IPهای مجاز SQL Server
5. صفحات تولید و بسته‌بندی تکمیل‌نشده
6. نیاز به پایش تمدید SSL
7. امکان افزودن WAL Archive و Point-in-Time Recovery در آینده

---

## 11. نتیجه تصمیم

استقرار WMS از نظر زیرساختی و جریان حواله عملیاتی است.

وضعیت نهایی:

- Frontend: عملیاتی
- Public API: عملیاتی
- Backend Recovery: آزمایش‌شده
- PostgreSQL: محدود به localhost
- Database Backup: زمان‌بندی‌شده و اعتبارسنجی‌شده
- HTTPS: فعال
- Security Headers: فعال
- Admin Credentials: تعویض‌شده
- Full Server Restart: آزمایش‌شده
- End-to-End Transfer: تأییدشده

تحویل نهایی منوط به تعیین تکلیف بکاپ خارج از سرور و پذیرش ریسک‌های ثبت‌شده توسط کارفرما است.
---

## 12. تصمیم‌های تکمیلی تولید و بسته‌بندی

### تصمیم 11: جداسازی پروفایل بسته‌بندی از موجودی کالا

برای هر محصول، پروفایل بسته‌بندی نسخه‌دار و اقلام آن به‌صورت مستقل ذخیره می‌شوند.

دلیل:
- امکان تغییر بسته‌بندی بدون تغییر ساختار محصول
- ثبت دقیق نوع، مقدار و مرحله مصرف
- حفظ تاریخچه نسخه‌ها

پیامد:
محصول فاقد پروفایل فعال، عمداً برای عملیات وابسته مسدود می‌شود.

### تصمیم 12: ثبت مستقل اجرای تولید

هر اجرای تولید شامل محصول، فرمول، مواد اولیه مصرفی و اقلام بسته‌بندی است.

دلیل:
- قابلیت ردیابی
- جلوگیری از کسر مبهم موجودی
- امکان رسیدگی به اختلاف‌ها

### تصمیم 13: اتصال بسته‌بندی به حواله انتقال

پیش از ثبت حواله، نیاز بسته‌بندی محاسبه و موجودی اقلام مرحله ارسال کنترل می‌شود.

پیامد:
در صورت کمبود بسته‌بندی ضروری، حواله ثبت نمی‌شود.

### تصمیم 14: Migration برگشت‌پذیر

تغییرات دیتابیس با فایل‌های Up و Down مستقل انجام شده و پیش از استقرار بکاپ تهیه شده است.

### تصمیم 15: عدم حذف فیزیکی داده‌های عملیاتی

برای کاربران، انبارها و در توسعه بعدی کالاها، غیرفعال‌سازی منطقی بر حذف فیزیکی ترجیح داده شد.

دلیل:
حفظ سوابق حواله، تولید، موجودی و حسابرسی.

---

## 13. اصلاح خرابی متن فارسی و PWA

در تاریخ 2026-07-27 تعداد 193 خط دارای متن `????` در Frontend شناسایی و اصلاح شد.

کنترل‌های انجام‌شده:

- حفظ نسخه اصلی و ایجاد Working Copy
- ذخیره UTF-8 بدون BOM
- Build آزمایشی ایزوله
- بررسی نبود `????` در Bundle
- انتشار با Asset نسخه‌دار
- جایگزینی `index.html` در مرحله آخر
- تنظیم Manifest روی `lang: fa` و `dir: rtl`
- تأیید عمومی سایت با HTTP 200

Rollback:

C:\warehouse\deployment_backups\frontend_before_textfix_20260727_075316

---

## 14. محدودیت مقیاس‌پذیری

PostgreSQL توان ذخیره حجم زیاد داده را دارد، اما نسخه فعلی برنامه برای یک تا دو میلیون کالای متمایز Benchmark نشده است.

موارد موکول‌شده به توسعه بعدی:

- Pagination و جستجوی سمت سرور
- ورود گروهی CSV
- Batch ID برای عملیات Import
- ایندکس‌گذاری و آزمون بار
- تنظیم Workerهای Backend
- غیرفعال‌سازی و فعال‌سازی مجدد کالا
- بازیابی امن رمز عبور
- پایش متمرکز سرویس، SSL، دیسک و بکاپ

---

## 15. وضعیت نهایی تحویل

- تولید و فرمولاسیون: عملیاتی
- پروفایل و موجودی بسته‌بندی: عملیاتی
- کنترل بسته‌بندی حواله: عملیاتی
- رسیدگی به مغایرت: عملیاتی
- متن فارسی Frontend: اصلاح‌شده
- PWA فارسی و RTL: تأییدشده
- Build و انتشار عمومی: تأییدشده
- محدودیت‌های توسعه آتی: در OPEN_RISKS.md ثبت‌شده

<!-- INVENTORY_EXCEL_FEATURE_20260730 -->

## الحاقیه: ورود موجودی اولیه و به‌روزرسانی موجودی با Excel

تاریخ استقرار: 2026-07-30

### دامنه قابلیت

این قابلیت فقط برای کاربر دارای نقش مدیر ارشد فعال است و سه عملیات زیر را ارائه می‌کند:

- دریافت فایل نمونه Excel
- بررسی و پیش‌نمایش بدون تغییر پایگاه داده
- ثبت نهایی اطلاعات در یک تراکنش پایگاه داده

### ساختار فایل

- برگه Inventory برای موجودی کالا اجباری است.
- برگه PackagingInventory اختیاری است و می‌تواند خالی باشد.
- برگه راهنما شامل توضیحات تکمیل فایل است.
- قالب تاریخ‌ها میلادی و به‌صورت YYYY-MM-DD است.

### رفتار ثبت

- کالا و بچ جدید در صورت معتبر بودن اطلاعات ساخته می‌شوند.
- موجودی موجود با کلید انبار، کالا و بچ به‌روزرسانی می‌شود.
- ورود مجدد همان فایل باعث ساخت رکورد موجودی تکراری نمی‌شود.
- موجودی بسته‌بندی موجود با کلید انبار و قلم بسته‌بندی به‌روزرسانی می‌شود.
- ثبت نهایی به‌صورت اتمیک انجام می‌شود؛ در صورت خطا کل تراکنش بازگردانده می‌شود.
- برای هر ثبت موفق، رویداد INVENTORY_EXCEL_IMPORT در جدول ثبت وقایع ذخیره می‌شود.

### اعتبارسنجی‌ها

- فقط فایل xlsx
- حداکثر حجم فایل: 10 مگابایت
- حداکثر 5000 ردیف در هر برگه
- جلوگیری از مقادیر منفی
- کنترل موجودی رزرو نسبت به موجودی کل
- الزام عدد صحیح برای تعداد اقلام بسته‌بندی
- کنترل نام انبار، کد کالا، بچ و اطلاعات پایه
- جلوگیری از ثبت فایل دارای خطا

### مسیرهای API

- GET /admin-panel/inventory-excel/template
- POST /admin-panel/inventory-excel/preview
- POST /admin-panel/inventory-excel/commit

تمام مسیرها تحت کنترل دسترسی مدیر ارشد هستند.

### آزمون‌های پذیرش انجام‌شده

- دریافت فایل نمونه
- ثبت اولیه کالا و بسته‌بندی
- به‌روزرسانی بدون ایجاد رکورد تکراری
- رد مقدار منفی
- پذیرش برگه اختیاری خالی
- رد تعداد اعشاری بسته‌بندی
- جلوگیری از دسترسی ناشناس با پاسخ HTTP 401
- کنترل نمایش قابلیت در نسخه عادی سایت و PWA
<!-- EMPLOYER_SCENARIO_PACKAGING_20260731 -->

## الحاقیه: اعتبارسنجی سناریوی کارفرما و الزام بسته‌بندی کالا

تاریخ آزمون و استقرار: 2026-07-31

### تصمیم‌های اجرایی

- انتقال همه انواع کالا، از جمله ماده اولیه، نیازمند پروفایل بسته‌بندی فعال است.
- کد بسته‌بندی اصلی در ورود Excel برای کالا الزامی است.
- قلم بسته‌بندی اصلی باید از نوع container باشد.
- ظرفیت بسته‌بندی اصلی نباید از وزن واحد کالا کمتر باشد.
- برای کالای جدید، ورود معتبر Excel یک پروفایل بسته‌بندی فعال با نسبت مصرف یک، مرحله dispatch و روش exact ایجاد می‌کند.
- برای کالای موجود، کد بسته‌بندی فایل باید با پروفایل فعال کالا یکسان باشد.
- هنگام ایجاد حواله، موجودی کالا و بسته‌بندی به‌صورت اتمیک کنترل و رزرو می‌شوند.
- در صورت کمبود بسته‌بندی یا نبود پروفایل فعال، حواله و رزرو ناقص ایجاد نمی‌شود.

### آزمون‌های پذیرش انجام‌شده

- ثبت موفق کالا، بچ، موجودی و بسته‌بندی از Excel
- ساخت خودکار پروفایل بسته‌بندی از Excel
- رزرو هم‌زمان کالا و بسته‌بندی
- کسر هم‌زمان کالا و بسته‌بندی هنگام خروج از مبدأ
- افزایش هم‌زمان کالا و بسته‌بندی هنگام دریافت در مقصد
- رد کد بسته‌بندی خالی
- رد کد بسته‌بندی ناموجود
- رد بسته‌بندی با ظرفیت ناکافی
- رد بسته‌بندی معتبر ولی غیر container
- رد ایجاد حواله در صورت کمبود بسته‌بندی
- تأیید عدم ایجاد رزرو ناقص پس از خطا
- رد انتقال کالای بدون پروفایل فعال
- رد مغایرت بسته‌بندی فایل با پروفایل فعال کالا
- Build موفق فرانت‌اند با Vite
- انتشار موفق فرانت‌اند با قابلیت Rollback
- اصلاح عنوان «محصول نهایی» به «کالا»
- پاسخ HTTP 200 فرانت‌اند و Backend پس از انتشار

### نتیجه

سناریوی سرتاسری ورود Excel، ساخت پروفایل، ایجاد حواله، خروج از مبدأ و دریافت در مقصد با کالا و بسته‌بندی همراه، با موفقیت تأیید شد.