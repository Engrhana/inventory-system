# Ethan's Variety Store Inventory System

A Django 6.0.3 inventory and sales management system for Ethan's Variety Store, built to track products, categories, stock movement, sales, and reports through a custom in-app interface.

Project documentation: `PROJECT_DOCUMENTATION_RESEARCH_FORMAT.md`

Live deployment: https://inventory-system-4lvc.onrender.com

## Overview

This project was built to manage Ethan's Variety Store from login to reporting. It includes role-based access, product and category management, sales recording with automatic stock updates, dashboard analytics, and export-ready reports.

## Main Features

- User authentication with login, logout, and in-app account signup.
- Role-based access:
  Admin users can manage categories, products, sales, and report exports.
  Standard users can log in and view dashboard, inventory, sales, and reports.
- Category management inside the app.
- Product management with category, price, and per-product low-stock thresholds.
- Stock-in/restock records with quantity, timestamp, user, and notes.
- POS-style sales recording with quick top-product selection, product search, purchased-item list, totals, tax, discount, payment, and change calculation.
- Automatic stock deduction when a sale is created or updated.
- Automatic stock restoration when a sale is deleted.
- Printable sale receipt for each recorded transaction.
- Low-stock monitoring using configurable per-product reorder thresholds.
- Dashboard metrics and charts for revenue, sales activity, and category mix.
- Date-filtered reports with tab-separated export and a print-friendly browser view for saving as PDF.
- Philippine timezone support using `Asia/Manila`, with user-facing timestamps labeled `PHT`.

## Data Model

The application uses these main models in `inventory/models.py`:

- `Category`
  Stores product group names such as Beverages or Snacks.
- `Product`
  Stores the product name, category, price, current stock quantity, and reorder threshold.
- `StockIn`
  Stores received stock shipments and increases product stock through an audit trail.
- `Sale`
  Stores the transaction header, user, and timestamp. Sales remain preserved even if the original staff account is later deleted.
- `SaleItem`
  Stores each product sold in a transaction, including quantity and subtotal.

### Why this structure matters

- It keeps the database normalized and easier to maintain.
- It allows one sale to contain multiple products.
- It supports accurate reporting by storing transaction history separately from current stock.
- It protects stock consistency through model-level save and delete logic.

## Core Workflows

### 1. Account Access

- Users can sign in at `/login/`.
- New standard accounts can be requested at `/register/`.
- Admin permissions are not assigned during signup; they must be granted by an administrator or superuser.
- Password reset URLs are available through Django's built-in authentication routes.
- Public signup is enabled for development/demo convenience. For production or internal-only deployments, disable self-signup or replace it with an approval-based onboarding flow.

### 2. Category Management

- Admin users can create, edit, and delete categories in the custom UI.
- A category cannot be deleted while products are still assigned to it.

### 3. Product Management

- Staff and admin users can add, edit, restock, and delete products from the inventory page.
- Stock quantity is increased by recording a stock-in/restock entry instead of manually editing the product count.
- A product cannot be deleted if it already appears in recorded sales history.
- If a product is tied to stock-in or sales history, the safer approach is to keep it and let sales reduce its stock to `0`.

### 4. Sales Management

- Staff and admin users can record a sale with one or more sale items.
- The record-sale screen is arranged like a simple POS:
  left side for the top 10 products and product search, right side for purchased items and payment totals.
- Frequently sold products can be added quickly from the top-product list.
- Products outside the top 10 can still be found through search.
- Tax, discount, amount paid, and change are calculated on-screen for cashier convenience.
- Saving a sale automatically reduces stock.
- Editing a sale recalculates stock safely.
- Deleting a sale restores stock quantities.
- Each saved sale includes a printable receipt view.

### 5. Reporting

- Signed-in users can view summary reports.
- Admin users can export reports as a tab-separated file or open a print-friendly browser page for saving as PDF.
- Reports can be filtered by start date and end date.

## Important Files

- `inventory/models.py`
  Contains the database models and stock protection logic.
- `inventory/forms.py`
  Contains signup, category, product, and sales form/formset logic.
- `inventory/views.py`
  Contains authentication, dashboard, category, inventory, sales, and report views.
- `inventory/urls.py`
  Contains the application routes.
- `inventory/admin.py`
  Contains the improved Django admin configuration.
- `inventory/templates/`
  Contains the custom UI templates.
- `inventory/tests.py`
  Contains automated tests for authentication, permissions, CRUD, stock logic, and reporting.
- `inventory_system/settings.py`
  Contains project settings, timezone configuration, and environment-aware debug/host settings.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run migrations:

```bash
python manage.py migrate
```

4. Create an administrator account:

```bash
python manage.py createsuperuser
```

5. Start the development server:

```bash
python manage.py runserver 8010
```

6. Open the app in your browser:

```text
http://127.0.0.1:8010/
```

## Optional Environment Variables

These are supported in `inventory_system/settings.py`:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `LOW_STOCK_THRESHOLD`
- `SITE_URL`
- `DATABASE_URL`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`

If these are not provided, the project still works locally using development defaults.

## Testing

Run the automated test suite with:

```bash
python manage.py test
```

The project currently includes tests for:

- login and signup
- permission checks
- category CRUD
- product CRUD
- sale stock updates
- report filtering and exports
- printable sale receipts
- timezone-aware report rendering

## Notes

- The project uses SQLite by default for local development.
- For production, set `DATABASE_URL` to a PostgreSQL database URL and install dependencies from `requirements.txt`.
- Keep `.env` out of commits and shared archives. If an app password or SMTP credential was exposed, revoke it in the provider console and replace it with a new value.
- The timezone is set to `Asia/Manila`.
- Django admin is available at `/admin/`, but the main product workflow is designed to work from the custom app pages.
- New signup accounts are standard users by default.
- The report download at `/reports/export/excel/` is a tab-separated export that opens well in spreadsheet tools.
- The PDF option renders a print-friendly HTML page intended for the browser's "Print / Save as PDF" flow.
