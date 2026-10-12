from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from shop.catalogue import CATEGORIES, PRODUCTS
from shop.models import Category, DiscountCode, Product, StockMovement

DEMO_PASSWORD = "Tradewind-2026"
ACCOUNTS = [
    # email, first name, last name, staff?, superuser?
    ("andrea@tradewind.test", "Andrea", "Cupid", True, True),
    ("shane@tradewind.test", "Shane", "Browne", True, False),
    ("kerry@example.test", "Kerry-Ann", "Baptiste", False, False),
    ("marlon@example.test", "Marlon", "Jack", False, False),
]


class Command(BaseCommand):
    help = "Fill an empty database with the demo catalogue, accounts and a discount code."

    def handle(self, *args, **options):
        if Product.objects.exists():
            raise CommandError("The shop already has products. Run `python manage.py flush` first to start again.")
        now = timezone.now()
        User = get_user_model()
        with transaction.atomic():
            for email, first, last, staff, superuser in ACCOUNTS:
                make = User.objects.create_superuser if superuser else User.objects.create_user
                make(username=email, email=email, password=DEMO_PASSWORD, first_name=first, last_name=last,
                     **({} if superuser else {"is_staff": staff}))
            categories = {name: Category.objects.create(name=name, slug=slugify(name)) for name in CATEGORIES}
            for sku, name, cat, price, vat, stock, description in PRODUCTS:
                p = Product.objects.create(sku=sku, name=name, slug=slugify(name), category=categories[cat],
                                           price_cents=price, vat_rate=vat, description=description)
                if stock:                     # opening stock goes through the ledger like any other delivery
                    p.stock = stock
                    p.save(update_fields=["stock"])
                    StockMovement.objects.create(product=p, change=stock, balance_after=stock, reason="restock",
                                                 note="opening stock", at=now)
            DiscountCode.objects.create(code="WELCOME10", percent_off=10, min_subtotal_cents=5000,
                                        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=90))

        self.stdout.write(self.style.SUCCESS(f"Added {len(PRODUCTS)} products in {len(CATEGORIES)} categories."))
        self.stdout.write(f"\nDemo logins (password for all: {DEMO_PASSWORD})")
        self.stdout.write("  andrea@tradewind.test   owner (full admin)")
        self.stdout.write("  shane@tradewind.test    shop staff")
        self.stdout.write("  kerry@example.test      customer")
        self.stdout.write("  marlon@example.test     customer")
        self.stdout.write("\nDiscount code WELCOME10: 10% off baskets of EC$50 or more.")
        self.stdout.write("Admin site: python manage.py runserver, then http://127.0.0.1:8000/admin/")
