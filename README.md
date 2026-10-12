# Tradewind

[![tests](https://github.com/Jody2905/tradewind/actions/workflows/tests.yml/badge.svg)](https://github.com/Jody2905/tradewind/actions/workflows/tests.yml)
![Django](https://img.shields.io/badge/Django-5.2%20LTS-0e5e6f)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.13-blue)
![Databases](https://img.shields.io/badge/database-SQLite%20%7C%20PostgreSQL-c8551f)

**An online shop for local goods, built with Django: a catalogue with live stock, a basket and checkout with VAT done properly, an order life cycle from payment to collection, a stock ledger that records every item in and out, and the staff tools and VAT reports a small shop actually runs on.**

> Tradewind is a portfolio project. The shop, products and prices are made up, and no real payments are taken.

| The shop | Basket with a discount code |
|---|---|
| ![Catalogue with stock labels](docs/screenshots/1-shop.png) | ![Basket with VAT and discount](docs/screenshots/2-basket.png) |
| **Order placed, paying by bank transfer** | **Staff overview** |
| ![Order page with bank details](docs/screenshots/3-order.png) | ![Staff dashboard](docs/screenshots/4-staff.png) |

---

## What it does

**For customers**
- Browse by category or search, with "Only 2 left" and "Out of stock" shown as it happens.
- A basket that works before logging in and is kept when you log in.
- Discount codes with start and end dates, usage limits and a minimum basket.
- Checkout: collect from the shop or have it delivered (free over EC$300); pay on collection or by bank transfer. **No card details are ever asked for**: taking cards safely needs a certified payment provider, so the shop doesn't pretend to.
- Order pages with the bank details, a pay-by date and progress; cancel an unpaid order yourself.

**For staff** (`/staff/`)
- An overview of what needs doing: orders to pack, ready to collect, awaiting payment (with overdue ones flagged), low stock and refunds due.
- Each order shows only its next step: record the payment with its reference, print a packing slip, mark it packed, then collected or delivered. Cancelling returns the stock; a paid order that's cancelled is flagged until the refund is recorded.
- Stock: record a delivery, or correct the stock after a physical count (a reason is required). Every product has its full history.
- **Sales & VAT** for any period: VAT collected split by 16% goods, 16% delivery and zero-rated goods, best sellers and sales per day, with an Excel download whose totals are live formulas.

![Sales and VAT report](docs/screenshots/6-sales.png)

---

## How the money works

- **Every amount is a whole number of cents**, never a float, so nothing is ever "off by a cent".
- **Prices include VAT**, as customers see them on the shelf. Basic foods (nutmeg, arrowroot) are zero-rated.
- **VAT is worked out per order line** on what was actually paid: `VAT = price × 16 / 116`, rounded half-up once per line.
- **Discounts are shared across the lines to the exact cent** (largest-remainder method), so each line's VAT is charged on its discounted amount and the lines always add up to the order total.
- **Prices and VAT are frozen on the order.** A price change tomorrow never alters an order placed today, so last month's VAT report never changes.
- **A sale counts on the day it was paid, in local time.** A payment at 11:30 p.m. in St Vincent is already the next day in UTC; it's reported on the local date, which is the one a VAT return uses. There's a test for exactly that midnight boundary.

## Design decisions

**Two customers buying the last item at the same moment.** Checkout locks the products being bought (`SELECT ... FOR UPDATE` on PostgreSQL; an immediate write lock on SQLite), always in the same order by id so two checkouts can never deadlock. A test has 10 customers try to buy the last 3 baskets at the same instant: it always ends with exactly 3 sales. With the lock removed, **PostgreSQL let all 10 customers buy the 3 baskets** (each checkout read "3 in stock" and saved over the others, a "lost update"), so the test is known to catch the problem.

**Checkout is all-or-nothing.** Re-pricing, the stock check, taking the stock, using the discount code and saving the order happen in one transaction. If anything fails, nothing is saved and no stock is taken.

**A stock ledger, not just a number.** Stock only ever changes through one function, which records a `StockMovement` (sold, returned, delivered, recounted) with the balance after it. A test checks that every product's stock equals its opening stock plus every movement. In the admin panel the ledger is read-only, even for the owner.

**The database enforces the rules too.** CHECK constraints refuse negative stock, a zero quantity, an order whose total doesn't equal subtotal − discount + delivery, a line whose total doesn't add up, delivery without an address, packing an order that was never paid, and a refund on an order that wasn't paid. Tests confirm each one.

**Orders follow a fixed path.** Awaiting payment → paid → packed → completed, or cancelled from any step before completion. Anything else is refused with a message saying why, and every step is recorded with who did it and when.

**Unpaid orders don't hold stock for ever.** They're cancelled after 2 days (pay on collection) or 3 days (bank transfer) by `python manage.py expire_unpaid_orders`, meant to run daily, or the button on the staff Orders page.

**One order per checkout.** Each checkout page carries a one-time token, so a double click or a browser refresh can't place the same order twice.

## Security

- Django's password hashing (PBKDF2) and password rules: at least 10 characters, not a common password, not similar to your name.
- **CSRF protection** on every form; every action that changes data is POST-only.
- **Customers see only their own orders.** Anyone else's order number gives "not found", which doesn't even confirm it exists. Staff pages do the same for non-staff.
- A **Content Security Policy** allows only the shop's own scripts and styles; pages are refused in frames; personal pages aren't cached.
- Checkout re-checks everything from the database; nothing in the basket (which lives in the session) is trusted for prices or stock.
- **Spreadsheet formula injection** blocked: a customer name such as `=HYPERLINK(...)` is written to Excel as text, never as a formula.
- Sign-up rejects an email already used by any account, and the "next page" after sign-up can't send people to another website.
- With `TRADEWIND_DEBUG=0` the settings switch to HTTPS-only cookies, HTTPS redirect and HSTS, and **`python manage.py check --deploy` passes with no warnings**. GitHub Actions runs that check on every push.

Tests prove the protections, not just the features: for the most important ones (overselling, order privacy, staff-only pages, double checkout, the Excel formula fix, the local-date VAT rule) the protection was removed on purpose to confirm a test fails without it.

## Run it

Needs Python 3.11 or newer.

```bash
git clone https://github.com/Jody2905/tradewind.git
cd tradewind
python -m pip install -r requirements-dev.txt

python manage.py migrate          # create the database (SQLite file)
python manage.py seed_demo        # 17 products, demo accounts and a month of orders
python manage.py runserver        # http://127.0.0.1:8000/  ·  staff pages at /staff/
```

(On Windows, `py` instead of `python` also works.)

Demo logins (password **`Tradewind-2026`**; discount code **`WELCOME10`**):

| Email | Who | Try |
|---|---|---|
| `kerry@example.test` | customer | shop, use WELCOME10, check out, see My orders |
| `marlon@example.test` | customer | |
| `shane@tradewind.test` | shop staff | Staff → record a payment, pack an order, Sales & VAT |
| `andrea@tradewind.test` | owner | everything, plus Django's admin panel |

To watch the shop's rules without a browser (nothing is saved):

```bash
python manage.py shop_demo
```

### With PostgreSQL

```bash
python -m pip install -r requirements-postgres.txt
$env:TRADEWIND_DATABASE_URL="postgresql://user:password@localhost:5432/tradewind"   # Windows PowerShell
export TRADEWIND_DATABASE_URL=postgresql://user:password@localhost:5432/tradewind   # macOS/Linux
python manage.py migrate
python manage.py seed_demo
```

### Development mode and production mode

By default the project runs in **development mode** (`DEBUG` on): errors show Django's detailed developer page, which helps while building but lists the site's internals. A real server sets `TRADEWIND_DEBUG=0`, its own `TRADEWIND_SECRET_KEY` and `TRADEWIND_ALLOWED_HOSTS`; visitors then see the shop's own friendly pages, and the HTTPS settings above switch on. In production mode Django doesn't serve the CSS itself: run `python manage.py collectstatic` and let the web server serve the `staticfiles/` folder.

## Tests

```bash
python -m pytest
```

Over 100 tests: money and VAT arithmetic, checkout, discounts, delivery, the order life cycle, refunds, stock and its ledger, simultaneous checkouts, database constraints, every customer and staff page, security (CSRF, privacy, staff-only pages, escaping, headers), the sales and VAT figures and the Excel export. They take a few seconds.

To run the same tests on PostgreSQL, set `TRADEWIND_DATABASE_URL` first (the user needs permission to create the test database).

GitHub Actions runs on every push: SQLite on Windows and Linux with Python 3.11 and 3.13 (including a check that no database migration was forgotten), a PostgreSQL 16 job, and Django's production security check.

## Project layout

```
config/             settings (database and secrets from environment variables) and URLs
shop/
  models.py         tables and the database constraints
  money.py          cents, VAT inside a price, exact discount sharing
  services.py       every rule: checkout, payment, packing, cancelling, refunds, stock
  basket.py         the session basket
  views.py          customer pages
  staff.py          staff pages
  reports.py        sales and VAT figures
  exports.py        Excel workbook
  admin.py          Django admin (orders and the stock ledger are read-only)
  migrations/       the database's history, one step per change
  management/commands/   seed_demo, shop_demo, expire_unpaid_orders
  templates/  static/
tests/              pytest suite
```

## Database

| Table | Holds |
|---|---|
| `Category`, `Product` | catalogue: SKU (unique), price in cents, VAT rate (16% or 0%), stock, low-stock alert level, active flag |
| `StockMovement` | every change to stock: product, change, balance after, reason, order, staff member, note |
| `DiscountCode` | percent off, valid dates, minimum basket, uses so far and maximum |
| `Order` | customer, status, payment and fulfilment method, address, frozen totals (subtotal, discount, delivery, total, VAT), pay-by date, payment and refund references and times |
| `OrderLine` | a snapshot of each item: SKU, name, unit price, quantity, VAT rate, its share of the discount, total and VAT |
| `OrderEvent` | the order's history: each status change, by whom, when and why |

Users are Django's built-in accounts; customers sign in with their email address, and staff have Django's `is_staff` flag.

## Possible next steps

- Email confirmations and "your order is ready" messages
- Product photos, and stock reserved for a few minutes while a customer is at checkout
- A card payment provider's hosted checkout (so card details never touch the shop's server)

---

Built by **Jody-Ann Trimmingham** · [GitHub](https://github.com/Jody2905)
