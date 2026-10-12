from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.db.models import Sum

from shop import services
from shop.models import DiscountCode, Order, Product, StockMovement
from shop.services import ShopError

from .conftest import NOW, items


def checkout(customer, products, discount="", fulfilment="collect", address="", payment="bank_transfer", **qty):
    return services.place_order(customer, items(products, **qty), payment, fulfilment, "784-555-0101",
                                delivery_address=address, discount_code=discount, now=NOW)


def test_order_totals_vat_and_number(customer, products):
    order = checkout(customer, products, hot_sauce=2, nutmeg=1)
    assert order.number == f"TW-{order.pk:06d}"
    assert order.subtotal_cents == 2 * 1160 + 850
    assert order.total_cents == 3170
    assert order.vat_cents == 320                         # 2 x 1.60 on the sauce; nutmeg is zero-rated
    lines = {line.sku: line for line in order.lines.all()}
    assert (lines["HS-01"].vat_cents, lines["NT-02"].vat_cents) == (320, 0)
    assert order.status == Order.Status.AWAITING_PAYMENT
    assert order.pay_by == NOW + timedelta(days=3)        # bank transfers get three days


def test_stock_is_taken_and_every_unit_recorded(customer, products):
    order = checkout(customer, products, hot_sauce=2, basket=3)
    assert Product.objects.get(sku="HS-01").stock == 18
    assert Product.objects.get(sku="BK-03").stock == 0
    sales = StockMovement.objects.filter(order=order, reason="sale")
    assert sorted((m.product.sku, m.change, m.balance_after) for m in sales) == [("BK-03", -3, 0), ("HS-01", -2, 18)]


def test_stock_always_equals_the_ledger(customer, staff, products):
    """However stock moves, opening stock + every movement = what's on the shelf."""
    opening = {p.id: p.stock for p in Product.objects.all()}
    order = checkout(customer, products, hot_sauce=5, basket=1)
    services.restock(staff, products["nutmeg"], 12, now=NOW)
    services.correct_stock(staff, products["hot_sauce"], 14, "one bottle broken", now=NOW)
    services.cancel_order(customer, order, "changed my mind", now=NOW)
    for p in Product.objects.all():
        moved = StockMovement.objects.filter(product=p).aggregate(t=Sum("change"))["t"] or 0
        assert p.stock == opening[p.id] + moved


def test_prices_are_frozen_on_the_order(customer, products):
    order = checkout(customer, products, basket=1)
    Product.objects.filter(sku="BK-03").update(price_cents=9900)       # price rise after the sale
    order.refresh_from_db()
    assert order.total_cents == 7500 and order.lines.get().unit_price_cents == 7500


def test_discount_is_shared_across_lines_and_vat_follows(customer, products, code):
    order = checkout(customer, products, discount="welcome10", hot_sauce=2, nutmeg=1, basket=1)
    assert order.subtotal_cents == 10670 and order.discount_cents == 1067 and order.discount_code == "WELCOME10"
    lines = list(order.lines.all())
    assert sum(line.discount_cents for line in lines) == 1067                 # every cent of the discount placed
    assert sum(line.line_total_cents for line in lines) == order.total_cents
    assert order.vat_cents == sum(line.vat_cents for line in lines)
    sauce = next(line for line in lines if line.sku == "HS-01")
    assert sauce.vat_cents == round((2320 - sauce.discount_cents) * 16 / 116)   # VAT on what was actually paid
    assert DiscountCode.objects.get().times_used == 1


@pytest.mark.parametrize("change, message", [
    ({"active": False}, "isn't valid"),
    ({"valid_until": NOW - timedelta(seconds=1), "valid_from": NOW - timedelta(days=9)}, "isn't valid"),
    ({"max_uses": 0}, "used up"),
    ({"min_subtotal_cents": 50000}, r"at least EC\$500\.00"),
])
def test_unusable_discount_codes(customer, products, code, change, message):
    DiscountCode.objects.filter(pk=code.pk).update(**change)
    with pytest.raises(ShopError, match=message):
        checkout(customer, products, discount="WELCOME10", hot_sauce=1)
    assert not Order.objects.exists()


def test_discount_use_limit(customer, other_customer, products, code):
    DiscountCode.objects.filter(pk=code.pk).update(max_uses=1)
    checkout(customer, products, discount="WELCOME10", hot_sauce=1)
    with pytest.raises(ShopError, match="used up"):
        checkout(other_customer, products, discount="WELCOME10", hot_sauce=1)


def test_delivery_fee_and_free_delivery(customer, products, code):
    small = checkout(customer, products, fulfilment="deliver", address="Kalan Green, Mesopotamia", hot_sauce=1)
    assert small.delivery_cents == 2500 and small.total_cents == 1160 + 2500
    assert small.vat_cents == 160 + 345                                         # delivery carries VAT too
    # The free-delivery threshold is checked after the discount: EC$306.20 less 10% is under EC$300
    almost = services.quote(items(products, basket=3, hot_sauce=7), "deliver", "WELCOME10", NOW)
    assert almost.subtotal_cents == 30620 and almost.subtotal_cents - almost.discount_cents < 30000
    assert almost.delivery_cents == 2500
    big = checkout(customer, products, fulfilment="deliver", address="Bay Street", basket=3, hot_sauce=7)
    assert big.subtotal_cents == 30620 and big.delivery_cents == 0


def test_not_enough_stock_saves_nothing(customer, products, code):
    with pytest.raises(ShopError, match="Only 3 Woven Palm Basket left"):
        checkout(customer, products, discount="WELCOME10", hot_sauce=1, basket=4)
    assert not Order.objects.exists()
    assert Product.objects.get(sku="HS-01").stock == 20                       # sauce not taken either
    assert DiscountCode.objects.get().times_used == 0                         # code not used up


def test_withdrawn_product_cannot_be_bought(customer, products):
    Product.objects.filter(sku="HS-01").update(active=False)
    with pytest.raises(ShopError, match="no longer sold"):
        checkout(customer, products, hot_sauce=1)


@pytest.mark.parametrize("kwargs, message", [
    ({}, "basket is empty"),
    ({"hot_sauce": 51}, "between 1 and 50"),
    ({"hot_sauce": -1}, "between 1 and 50"),
])
def test_basket_validation(customer, products, kwargs, message):
    with pytest.raises(ShopError, match=message):
        checkout(customer, products, **kwargs)


def test_delivery_needs_an_address_and_everyone_a_phone(customer, products):
    with pytest.raises(ShopError, match="delivery address"):
        checkout(customer, products, fulfilment="deliver", hot_sauce=1)
    with pytest.raises(ShopError, match="phone"):
        services.place_order(customer, items(products, hot_sauce=1), "collection", "collect", " ", now=NOW)


def test_database_refuses_impossible_data(customer, products):
    """The constraints catch mistakes even when code skips the rules."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.filter(sku="BK-03").update(stock=-1)
    order = checkout(customer, products, hot_sauce=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.filter(pk=order.pk).update(total_cents=1)               # doesn't add up
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.filter(pk=order.pk).update(status="packed")             # packed but never paid
