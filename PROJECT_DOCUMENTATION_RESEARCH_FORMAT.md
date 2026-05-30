Ethan's Variety Store Inventory System

Project Documentation in Research Format

Project Title: Ethan's Variety Store Inventory System  
Technology Used: Python, Django, SQLite, HTML, CSS, JavaScript, Bootstrap  
GitHub Link: Replace this line with your GitHub repository link before submission.

Abstract

Ethan's Variety Store Inventory System is a web-based inventory and sales management system developed using Django. The system was designed to help a small retail store manage products, categories, stock movement, sales transactions, receipts, and reports in one application. The project addresses common inventory problems such as manual stock tracking, delayed sales recording, low-stock monitoring, and inaccurate transaction history. The system includes authentication, role-based access, barcode-supported product search, stock-in records, automatic stock deduction during sales, automatic stock restoration when sales are deleted, dashboard analytics, and report exports. Testing was performed using Django's built-in test framework, with 60 automated tests covering authentication, permissions, CRUD operations, stock logic, reports, receipts, and barcode search behavior.

1. Introduction

Small retail stores often rely on manual notebooks or spreadsheets to track products and sales. This method can lead to inaccurate stock counts, missing sales records, difficulty identifying low-stock products, and slow report preparation. Ethan's Variety Store Inventory System was created to provide a centralized and easy-to-use web application for managing daily store operations.

The system supports product inventory management, stock-in records, sales recording, receipt generation, and reporting. It also includes barcode search support to make product lookup faster during inventory checking and sales transactions.

2. Statement of the Problem

The project aims to address the following problems:

1. Manual inventory tracking can cause inaccurate stock records.
2. Store staff may have difficulty identifying products that need restocking.
3. Sales records may be incomplete or difficult to summarize manually.
4. Product lookup can be slow when there are many products.
5. Reports are time-consuming to prepare without an automated system.

3. Objectives

The general objective of this project is to develop a web-based inventory and sales management system for Ethan's Variety Store.

The specific objectives are:

1. To provide secure login, logout, registration, and role-based access.
2. To allow authorized users to manage product categories and product records.
3. To support barcode-based product searching.
4. To record stock-in transactions and automatically update product stock.
5. To record sales and automatically deduct sold quantities from inventory.
6. To restore product stock when a sale is deleted.
7. To provide dashboards and reports for inventory and sales monitoring.
8. To verify system behavior through automated backend tests.

4. Scope and Limitations

The system covers the following features:

1. User authentication and account request workflow.
2. Admin, staff, and standard user access control.
3. Product category management.
4. Product management with name, barcode, category, price, stock count, and reorder threshold.
5. Stock-in or restock recording.
6. POS-style sales recording with product search, tax, discount, amount paid, and change calculation.
7. Printable sale receipts.
8. Inventory dashboard and low-stock monitoring.
9. Date-filtered reports and tab-separated report export.

The system has the following limitations:

1. The default local database is SQLite, which is suitable for development and small-scale use.
2. The PDF report uses the browser's print or save-as-PDF feature.
3. Barcode scanning depends on the scanner behaving like keyboard input.
4. The system does not include online payment processing.

5. Methodology

The project followed an iterative development approach. The system was divided into modules such as authentication, product management, stock management, sales management, reporting, and testing. Each module was implemented and tested before being integrated into the full application.

The main development steps were:

1. Identify store inventory and sales requirements.
2. Design the database models for users, categories, products, stock-in records, sales, and sale items.
3. Build Django views, forms, templates, and URL routes.
4. Implement business rules for stock deduction, stock restoration, and low-stock monitoring.
5. Add barcode fields and barcode-supported searching.
6. Create automated tests for important workflows.
7. Run migrations, system checks, and test suite validation.

6. System Design

The system uses Django's Model-View-Template architecture.

The models define the database structure and business rules. The views handle user requests, filtering, form processing, sales transactions, and report generation. The templates provide the user interface for dashboards, inventory pages, sales pages, receipts, and reports.

Main Modules

1. Authentication Module  
   Handles login, logout, registration, account requests, and password reset pages.

2. Inventory Module  
   Handles category management, product management, barcode search, stock monitoring, and stock history.

3. Stock-In Module  
   Records incoming stock and automatically increases product quantity.

4. Sales Module  
   Records sales transactions, calculates totals, deducts stock, and generates receipts.

5. Reports Module  
   Displays sales and inventory summaries with date filters and export support.

6. Admin Module  
   Provides Django admin support for managing data directly when needed.

7. Database Design

The main database entities are:

1. `AccountRequest`  
   Stores pending, approved, or rejected account requests.

2. `Category`  
   Stores product category names.

3. `Product`  
   Stores product name, barcode, category, stock quantity, reorder threshold, and price.

4. `StockIn`  
   Stores stock-in quantity, date received, staff user, and notes.

5. `Sale`  
   Stores sales transaction details such as user, date, tax, discount, amount paid, grand total, and change.

6. `SaleItem`  
   Stores each product included in a sale, including quantity and subtotal.

8. Implementation

The application was implemented using Django 6.0.3. SQLite is used by default for local development. The system includes server-side validation through Django forms and model methods. Stock consistency is protected by model-level save and delete logic using database transactions.

Important implementation details include:

1. Product stock is not edited directly during normal workflows.
2. Stock increases are recorded through `StockIn`.
3. Sales automatically reduce product stock.
4. Sale deletion restores the sold quantities.
5. Barcode values are trimmed before saving.
6. Blank barcodes are stored as empty database values so multiple products can exist without barcodes.
7. Inventory and sales search support product names, categories, and barcodes.

9. Testing and Evaluation

The system was tested using Django's automated testing framework. The test suite contains 60 tests.

The tests cover:

1. Login and registration.
2. Account approval behavior.
3. Role-based permission checks.
4. Category create, update, and delete operations.
5. Product create, update, delete, and barcode handling.
6. Inventory search by name and barcode.
7. Stock-in behavior.
8. Sale creation, update, deletion, and stock recalculation.
9. Duplicate product validation in sales.
10. Sales receipt rendering.
11. Report filtering and exports.
12. Timezone-aware report rendering.

Validation commands used:

```bash
python manage.py migrate
python manage.py check
python manage.py test --verbosity 1
```

Expected successful result:

```text
System check identified no issues (0 silenced).
Ran 60 tests in ...
OK
```

10. Results

The project successfully provides an inventory and sales management system for Ethan's Variety Store. The system can manage products, track stock-in records, process sales, generate receipts, monitor low-stock products, and display reports. Barcode-supported search improves product lookup in both inventory browsing and sales recording. Automated tests confirm that the main backend workflows are working correctly.

11. Conclusion

Ethan's Variety Store Inventory System helps improve store operations by replacing manual inventory and sales tracking with a centralized web-based system. The project reduces the risk of stock errors, improves sales recording, and makes reporting easier. Based on testing results, the backend behavior is stable and the major workflows are functioning as expected.

12. Recommendations

Future improvements may include:

1. Deployment to a production server.
2. PostgreSQL database setup for larger-scale use.
3. Real PDF generation instead of browser print-to-PDF.
4. More detailed audit logs for edited sales and product changes.
5. Supplier management.
6. Purchase order management.
7. Backup and restore tools.

References

1. Django Software Foundation. Django Documentation. https://docs.djangoproject.com/
2. Python Software Foundation. Python Documentation. https://docs.python.org/
3. Bootstrap Documentation. https://getbootstrap.com/docs/

Appendix

Local Setup Commands

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8010
```

Local Application URL

```text
http://127.0.0.1:8010/
```

Submission Reminder

Before submitting, replace the GitHub link placeholder near the top of this document with your actual repository URL.
