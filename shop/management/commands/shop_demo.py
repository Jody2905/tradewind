"""A walkthrough of the shop's rules, printed step by step.

    python manage.py shop_demo

Everything happens inside a database transaction that is rolled back at the
end, so it never changes the real shop.
"""

from datetime import datetime, timedelta, timezone as tz

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from shop import services
from shop.models import Category, DiscountCode, Product
from shop.money import fmt
from shop.services import ShopError

T0 = datetime(2026, 11, 2, 14, 0, tzinfo=tz.utc)


class Command(BaseCommand):
    help = "Walk through the shop's rules (nothing is saved)."

    def handle(self, *args, **options):
        with transaction.atomic():
            self._walkthrough()
            transaction.set_rollback(True)
        self.out("\n(Demo finished: everything above was rolled back, so the shop is unchanged.)")

    def out(self, text=""):
        self.stdout.write(text)

    def step(self, title):
        self.out("")
        self.out(f"== {title} " + "=" * max(0, 66 - len(title)))

    def refused(self, action):
        try:
            action()
            self.out("   !! expected this to be refused")
        except ShopError as e:
            self.out(f"   REFUSED: {e}")

    def _walkthrough(self):
        User = get_user_model()
        staff = User.objects.create_user("demo-staff", password="x", is_staff=True)
        kerry = User.objects.create_user("demo-kerry", password="x", first_name="Kerry-Ann")
        marlon = User.objects.create_user("demo-marlon", password="x", first_name="Marlon")
        cat = Category.objects.create(name="Demo goods", slug="demo-goods")

        def product(sku, name, price, stock, vat=16):
            return Product.objects.create(sku=f"DEMO-{sku}", name=name, slug=f"demo-{sku.lower()}", category=cat,
                                          price_cents=price, stock=stock, vat_rate=vat)
        sauce = product("HOT", "Scotch Bonnet Hot Sauce", 1160, 20)
        nutmeg = product("NUT", "Whole Nutmeg 100g", 850, 10, vat=0)
        basket = product("BSK", "Woven Palm Basket", 7500, 3)
        DiscountCode.objects.create(code="DEMO10", percent_off=10, min_subtotal_cents=5000,
                                    valid_from=T0 - timedelta(days=1), valid_until=T0 + timedelta(days=30))

        self.step("The catalogue (prices include VAT)")
        for p in (sauce, nutmeg, basket):
            self.out(f"   {p.name:<26} {fmt(p.price_cents):>10}   VAT {p.vat_rate:>2}%   {p.stock} in stock")

        self.step("Rule: VAT is worked out per line, on what was actually paid")
        q = services.quote({sauce.id: 2, nutmeg.id: 1, basket.id: 1}, "collect", "DEMO10", T0)
        for line in q.lines:
            self.out(f"   {line.quantity} x {line.product.name:<26} {fmt(line.gross_cents):>10}"
                     f"  less {fmt(line.discount_cents):>8}  = {fmt(line.total_cents):>10}  (VAT {fmt(line.vat_cents)})")
        self.out(f"   Subtotal {q.subtotal}, discount DEMO10 -{q.discount}, total {q.total}, of which VAT {q.vat}")
        self.out("   The discount is shared across the lines to the cent, so the lines add up exactly to the total.")

        self.step("Rule: stock is taken at checkout and every unit is recorded")
        order = services.place_order(kerry, {sauce.id: 2, basket.id: 2}, "bank_transfer", "collect",
                                     "784-555-0101", now=T0)
        basket.refresh_from_db()
        self.out(f"   Kerry-Ann places {order.number}: {order.total}, pay by {order.pay_by:%d %b} (3 days for a transfer)")
        self.out(f"   Baskets left: {basket.stock}")

        self.step("Rule: you can't buy more than is on the shelf")
        self.refused(lambda: services.place_order(marlon, {basket.id: 2}, "collection", "collect", "784-555-0102", now=T0))
        self.out("   (Nothing was saved and no stock was taken: the whole checkout is one transaction.)")

        self.step("Rule: orders follow a fixed path")
        self.refused(lambda: services.mark_packed(staff, order, now=T0))
        services.mark_paid(staff, order, "FCIB-88213", now=T0 + timedelta(hours=4))
        self.out("   Staff record the bank transfer FCIB-88213 -> paid")
        self.refused(lambda: services.cancel_order(kerry, order, "changed my mind", now=T0 + timedelta(hours=5)))

        self.step("Rule: cancelling puts the stock back")
        services.cancel_order(staff, order, "customer asked by phone", now=T0 + timedelta(hours=6))
        basket.refresh_from_db()
        order.refresh_from_db()
        self.out(f"   Staff cancel {order.number}: baskets back to {basket.stock}; refund due: {'yes' if order.refund_due else 'no'}")

        self.step("Rule: unpaid orders expire and release their stock")
        later = T0 + timedelta(hours=7)
        unpaid = services.place_order(marlon, {basket.id: 3}, "collection", "collect", "784-555-0102", now=later)
        basket.refresh_from_db()
        self.out(f"   Marlon reserves all {3 - basket.stock} baskets with {unpaid.number}, pay on collection within 2 days")
        expired = services.expire_unpaid_orders(now=later + timedelta(days=2, minutes=1))
        basket.refresh_from_db()
        self.out(f"   Two days later: {', '.join(o.number for o in expired)} cancelled; baskets back to {basket.stock}")

        self.step("The stock ledger for Woven Palm Basket")
        for m in reversed(basket.movements.all()):
            self.out(f"   {m.at:%d %b %H:%M}  {m.change:+3d}  -> {m.balance_after:>2}  {m.get_reason_display()}")
