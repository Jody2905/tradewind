# Tradewind

An online shop for local goods, built with **Django**: a product catalogue with stock, carts and checkout, VAT-inclusive pricing with per-line VAT, discount codes, an order life cycle from payment to collection, and a stock ledger that records every item in and out.

> Work in progress. The database, the shop's rules and the customer pages are done; staff tools and full documentation follow.

## Try it

```bash
python -m pip install -r requirements-dev.txt
python manage.py migrate          # create the database
python manage.py shop_demo        # walk through the rules (saves nothing)
python manage.py seed_demo        # demo products and accounts
python manage.py runserver        # shop at http://127.0.0.1:8000/  (admin at /admin/)
python -m pytest                  # run the tests
```

Demo logins (password `Tradewind-2026`; discount code `WELCOME10`): **andrea@tradewind.test** (owner), **shane@tradewind.test** (staff), **kerry@example.test** and **marlon@example.test** (customers).

Built by **Jody-Ann Trimmingham** · [GitHub](https://github.com/Jody2905)
