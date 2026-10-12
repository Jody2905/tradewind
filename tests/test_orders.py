from datetime import timedelta

import pytest

from shop import services
from shop.models import Order, Product, StockMovement
from shop.services import NotAllowed, ShopError

from .conftest import NOW, items


@pytest.fixture
def order(customer, products):
    return services.place_order(customer, items(products, hot_sauce=2, basket=1), "bank_transfer", "collect",
                                "784-555-0101", now=NOW)


def stock(sku):
    return Product.objects.get(sku=sku).stock


def test_full_life_cycle(staff, order):
    services.mark_paid(staff, order, "FCIB-88213", now=NOW + timedelta(hours=5))
    services.mark_packed(staff, order, now=NOW + timedelta(hours=6))
    done = services.mark_completed(staff, order, now=NOW + timedelta(days=1))
    assert done.status == "completed" and done.payment_reference == "FCIB-88213"
    assert [(e.from_status, e.to_status) for e in done.events.all()] == [
        ("", "awaiting_payment"), ("awaiting_payment", "paid"), ("paid", "packed"), ("packed", "completed")]
    assert done.events.last().note == "collected"


def test_steps_cannot_be_skipped(staff, order):
    with pytest.raises(ShopError, match="awaiting payment, so it can't be marked packed"):
        services.mark_packed(staff, order)
    services.mark_paid(staff, order, "REF1")
    with pytest.raises(ShopError, match="can't be marked paid"):
        services.mark_paid(staff, order, "REF2")                    # no double payment


def test_payment_needs_a_reference(staff, order):
    with pytest.raises(ShopError, match="payment reference"):
        services.mark_paid(staff, order, "  ")


def test_only_staff_move_orders_along(customer, order):
    with pytest.raises(NotAllowed):
        services.mark_paid(customer, order, "I paid honestly")
    assert Order.objects.get(pk=order.pk).status == "awaiting_payment"


def test_customer_cancels_unpaid_order_and_stock_returns(customer, order):
    assert (stock("HS-01"), stock("BK-03")) == (18, 2)
    cancelled = services.cancel_order(customer, order, "ordered the wrong size", now=NOW)
    assert cancelled.status == "cancelled" and not cancelled.refund_due
    assert (stock("HS-01"), stock("BK-03")) == (20, 3)
    assert StockMovement.objects.filter(order=order, reason="return").count() == 2


def test_customer_cannot_cancel_after_paying_or_cancel_others(customer, other_customer, staff, order):
    with pytest.raises(NotAllowed, match="your own"):
        services.cancel_order(other_customer, order, "not mine")
    services.mark_paid(staff, order, "REF1")
    with pytest.raises(NotAllowed, match="contact the shop"):
        services.cancel_order(customer, order, "too late")


def test_staff_cancel_paid_order_flags_refund(staff, order):
    services.mark_paid(staff, order, "REF1")
    services.mark_packed(staff, order)
    cancelled = services.cancel_order(staff, order, "customer moved away")
    assert cancelled.refund_due
    assert stock("BK-03") == 3


def test_completed_or_cancelled_orders_cannot_be_cancelled(customer, staff, order):
    services.cancel_order(customer, order, "first cancel")
    with pytest.raises(ShopError, match="cancelled, so it can't be marked cancelled"):
        services.cancel_order(staff, order, "second cancel")
    assert stock("HS-01") == 20                                     # stock returned once, not twice


def test_cancel_needs_a_reason(customer, order):
    with pytest.raises(ShopError, match="reason"):
        services.cancel_order(customer, order, "")


def test_unpaid_orders_expire_and_release_stock(customer, staff, products, order):
    paid = services.place_order(customer, items(products, nutmeg=1), "collection", "collect", "784-555-0101", now=NOW)
    services.mark_paid(staff, paid, "CASH-01")
    assert services.expire_unpaid_orders(now=NOW + timedelta(days=2, hours=23)) == []      # not yet
    expired = services.expire_unpaid_orders(now=NOW + timedelta(days=3, minutes=1))
    assert [o.pk for o in expired] == [order.pk]
    assert Order.objects.get(pk=order.pk).cancel_reason == "Not paid by the deadline"
    assert Order.objects.get(pk=paid.pk).status == "paid"
    assert stock("BK-03") == 3


def test_restock_and_stock_count(staff, products):
    services.restock(staff, products["basket"], 5, "from Ms. Ollivierre", now=NOW)
    assert stock("BK-03") == 8
    services.correct_stock(staff, products["basket"], 7, "one damaged in storage", now=NOW)
    assert stock("BK-03") == 7
    moves = list(StockMovement.objects.filter(product=products["basket"]).order_by("id"))
    assert [(m.reason, m.change, m.balance_after) for m in moves] == [("restock", 5, 8), ("adjustment", -1, 7)]


def test_stock_rules(customer, staff, products):
    with pytest.raises(NotAllowed):
        services.restock(customer, products["basket"], 5)
    with pytest.raises(ShopError, match="at least 1"):
        services.restock(staff, products["basket"], 0)
    with pytest.raises(ShopError, match="nothing to correct"):
        services.correct_stock(staff, products["basket"], 3, "recount")
    with pytest.raises(ShopError, match="why"):
        services.correct_stock(staff, products["basket"], 2, "")
