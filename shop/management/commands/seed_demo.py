import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from shop.catalogue import CATEGORIES, PRODUCTS
from shop import services
from shop.models import Category, DiscountCode, Order, Product, StockMovement

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
        self.password = make_password(DEMO_PASSWORD)    # hashing is slow on purpose, so do it once for all demo accounts
        with transaction.atomic():
            for email, first, last, staff, superuser in ACCOUNTS:
                User.objects.create(username=email, email=email, password=self.password, first_name=first,
                                    last_name=last, is_staff=staff, is_superuser=superuser)
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
                                        valid_from=now - timedelta(days=60), valid_until=now + timedelta(days=90))
            orders = self._history(now)

        self.stdout.write(self.style.SUCCESS(f"Added {len(PRODUCTS)} products in {len(CATEGORIES)} categories "
                                             f"and {orders} orders from the last 30 days."))
        self.stdout.write(f"\nDemo logins (password for all: {DEMO_PASSWORD})")
        self.stdout.write("  andrea@tradewind.test   owner (full admin)")
        self.stdout.write("  shane@tradewind.test    shop staff")
        self.stdout.write("  kerry@example.test      customer")
        self.stdout.write("  marlon@example.test     customer")
        self.stdout.write("\nDiscount code WELCOME10: 10% off baskets of EC$50 or more.")
        self.stdout.write("Admin site: python manage.py runserver, then http://127.0.0.1:8000/admin/")


    def _history(self, now):
        """A month of realistic orders so the staff pages and reports have something to show."""
        rng = random.Random(7)                           # the same demo every time
        User = get_user_model()
        staff = User.objects.get(username="shane@tradewind.test")
        names = [("Akeem", "Adams"), ("Brianna", "Charles"), ("Chevonne", "Daniel"), ("Darnell", "Francis"),
                 ("Ellisha", "George"), ("Fabian", "Harry"), ("Gillian", "John"), ("Hadiya", "King"),
                 ("Isaiah", "Lynch"), ("Latoya", "Nanton")]
        customers = [User.objects.create(username=f"{f.lower()}.{l.lower()}@example.test",
                                         email=f"{f.lower()}.{l.lower()}@example.test",
                                         password=self.password, first_name=f, last_name=l) for f, l in names]
        customers += list(User.objects.filter(username__in=["kerry@example.test", "marlon@example.test"]))
        products = list(Product.objects.exclude(sku="TC-NIB"))      # cocoa nibs stay out of stock
        local_now = timezone.localtime(now)
        count = 0
        for days_ago in range(30, -1, -1):
            for _ in range(rng.choice([0, 1, 1, 2, 2, 3])):
                placed = (local_now - timedelta(days=days_ago)).replace(
                    hour=rng.randint(8, 19), minute=rng.randint(0, 59), second=0, microsecond=0)
                if placed >= local_now:
                    continue
                basket = {}
                for p in rng.sample(products, rng.choice([1, 1, 2, 2, 3])):
                    qty = rng.choice([1, 1, 1, 2, 3])
                    p.refresh_from_db()
                    if p.stock < qty + 1:                # the shop restocks before running out
                        services.restock(staff, p, 24, "supplier delivery", now=placed - timedelta(hours=2))
                    basket[p.id] = qty
                fulfilment = rng.choice(["collect", "collect", "deliver"])
                order = services.place_order(
                    rng.choice(customers), basket, rng.choice(["collection", "bank_transfer"]), fulfilment,
                    f"784-555-{rng.randint(1000, 9999)}", delivery_address="Kingstown Park" if fulfilment == "deliver" else "",
                    discount_code="WELCOME10" if rng.random() < .2 and sum(
                        Product.objects.get(pk=i).price_cents * q for i, q in basket.items()) >= 5000 else "",
                    now=placed)
                count += 1
                self._progress(order, staff, placed, local_now, rng)
        # Release orders that went unpaid more than a day ago
        services.expire_unpaid_orders(now=now - timedelta(days=1))

        # A few of today's situations, so every part of the staff dashboard has something in it
        def today(hours_ago, customer, basket, payment="collection", fulfilment="collect"):
            nonlocal count
            count += 1
            return services.place_order(customer, {p.id: q for p, q in basket}, payment, fulfilment, "784-555-0199",
                                        delivery_address="Kingstown Park" if fulfilment == "deliver" else "",
                                        now=now - timedelta(hours=hours_ago))
        by_sku = {p.sku: p for p in products}
        overdue = today(3 * 24 + 5, customers[3], [(by_sku["PN-CAK"], 1)], "bank_transfer")     # pay-by passed 5 hours ago
        for i, sku in enumerate(["CR-SCF", "BB-BAY"]):                                          # packed, ready to collect
            o = today(6 - i, customers[4 + i], [(by_sku[sku], 1), (by_sku["PN-HOT"], 2)])
            services.mark_paid(staff, o, f"RCPT-7700{i}", now=now - timedelta(hours=4 - i))
            services.mark_packed(staff, o, now=now - timedelta(hours=2 - i))
        o = today(3, customers[6], [(by_sku["CR-BWL"], 1)], "bank_transfer", "deliver")        # paid, to pack
        services.mark_paid(staff, o, "BT-55120", now=now - timedelta(hours=1))
        today(1, customers[7], [(by_sku["TC-LEM"], 2), (by_sku["PN-GUA"], 1)])                  # just placed
        assert overdue.status == Order.Status.AWAITING_PAYMENT
        return count

    def _progress(self, order, staff, placed, now, rng):
        age = now - placed
        roll = rng.random()
        if roll < .07:
            services.cancel_order(order.customer, order, "changed my mind", now=placed + timedelta(hours=3))
            return
        if roll < .14 or age < timedelta(hours=rng.randint(4, 30)):
            return                                       # never paid (expires later) or still waiting
        paid = placed + timedelta(hours=rng.randint(1, 40))
        if paid >= now:
            return
        services.mark_paid(staff, order, f"{'BT' if order.payment_method == 'bank_transfer' else 'RCPT'}-{rng.randint(10000, 99999)}", now=paid)
        if rng.random() < .04:
            services.cancel_order(staff, order, "customer asked to cancel by phone", now=paid + timedelta(hours=2))
            return
        packed = paid + timedelta(hours=rng.randint(2, 20))
        if packed >= now:
            return
        services.mark_packed(staff, order, now=packed)
        done = packed + timedelta(hours=rng.randint(3, 48))
        if done < now:
            services.mark_completed(staff, order, now=done)
