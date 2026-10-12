"""The shop's rules. Views, admin actions and tests all go through these functions.

Checkout is the important one. In a single database transaction it:
  1. locks the products being bought (always in the same order, by id, so two
     checkouts can never wait on each other forever: no deadlocks)
  2. re-checks price, availability and stock while holding the locks
  3. takes the stock, records a StockMovement for every item, and saves the
     order with its prices and VAT frozen
If anything fails, nothing is saved and no stock is taken.

Order life cycle (anything else is refused):

    awaiting_payment --paid--> paid --packed--> packed --completed--> completed
           |                     |                 |
           +------ cancelled <---+-----------------+   (stock goes back on the shelf)
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import DiscountCode, Order, OrderEvent, OrderLine, Product, StockMovement
from .money import allocate, fmt, percent_of, vat_included

MAX_PER_LINE = 50
S = Order.Status


class ShopError(Exception):
    """A rule said no. The message is safe to show to the customer."""


class NotAllowed(ShopError):
    pass


# ======================================================================
# Pricing a basket (used by the cart page and again inside checkout)
# ======================================================================

@dataclass
class QuoteLine:
    product: Product
    quantity: int
    gross_cents: int            # unit price x quantity
    discount_cents: int = 0
    total_cents: int = 0
    vat_cents: int = 0


@dataclass
class Quote:
    lines: list
    subtotal_cents: int
    discount_cents: int
    discount_code: str
    delivery_cents: int
    delivery_vat_cents: int
    total_cents: int
    vat_cents: int
    problems: list = field(default_factory=list)      # reasons the basket can't be ordered as it is

    def __getattr__(self, name):                       # .subtotal, .total, ... -> "EC$12.34"
        if name in ("subtotal", "discount", "delivery", "total", "vat"):
            return fmt(getattr(self, f"{name}_cents"))
        raise AttributeError(name)


def quote(items, fulfilment="collect", discount_code="", now=None, products=None):
    """Price a basket. `items` maps product id -> quantity."""
    now = now or timezone.now()
    if products is None:
        products = {p.id: p for p in Product.objects.filter(id__in=items.keys())}
    lines, problems = [], []
    for product_id, quantity in sorted(items.items()):
        product = products.get(product_id)
        if product is None or not product.active:
            problems.append("An item in your basket is no longer sold and was removed.")
            continue
        if quantity > product.stock:
            problems.append(f"Only {product.stock} {product.name} left in stock." if product.stock
                            else f"{product.name} is out of stock.")
        lines.append(QuoteLine(product, quantity, product.price_cents * quantity))

    subtotal = sum(line.gross_cents for line in lines)
    discount, code = 0, ""
    if discount_code:
        try:
            dc = _usable_discount(discount_code, subtotal, now)
            discount, code = percent_of(subtotal, dc.percent_off), dc.code
        except ShopError as e:
            problems.append(str(e))

    # Share the discount across lines so each line's VAT is charged on what was actually paid
    for line, share in zip(lines, allocate(discount, [line.gross_cents for line in lines])):
        line.discount_cents = share
        line.total_cents = line.gross_cents - share
        line.vat_cents = vat_included(line.total_cents, line.product.vat_rate)

    delivery = 0
    if fulfilment == Order.Fulfilment.DELIVER and lines and subtotal - discount < settings.FREE_DELIVERY_FROM_CENTS:
        delivery = settings.DELIVERY_FEE_CENTS
    delivery_vat = vat_included(delivery, 16)
    return Quote(lines, subtotal, discount, code, delivery, delivery_vat, subtotal - discount + delivery,
                 sum(line.vat_cents for line in lines) + delivery_vat, problems)


def _usable_discount(code, subtotal, now, lock=False):
    qs = DiscountCode.objects.select_for_update() if lock else DiscountCode.objects
    dc = qs.filter(code=code.strip().upper()).first()
    if dc is None or not dc.active or not (dc.valid_from <= now < dc.valid_until):
        raise ShopError(f"The code {code.strip().upper()!r} isn't valid.")
    if dc.max_uses is not None and dc.times_used >= dc.max_uses:
        raise ShopError(f"The code {dc.code} has been used up.")
    if subtotal < dc.min_subtotal_cents:
        raise ShopError(f"The code {dc.code} needs a basket of at least {fmt(dc.min_subtotal_cents)}.")
    return dc


# ======================================================================
# Checkout
# ======================================================================

def place_order(customer, items, payment_method, fulfilment, phone, delivery_address="",
                discount_code="", now=None):
    now = now or timezone.now()
    items = {int(pid): int(qty) for pid, qty in items.items() if int(qty) != 0}
    if not items:
        raise ShopError("Your basket is empty.")
    if any(qty < 0 or qty > MAX_PER_LINE for qty in items.values()):
        raise ShopError(f"You can order between 1 and {MAX_PER_LINE} of each item.")
    if payment_method not in Order.Payment.values or fulfilment not in Order.Fulfilment.values:
        raise ShopError("Please choose how to pay and how to receive your order.")
    if not phone.strip():
        raise ShopError("Please give a phone number so we can contact you about your order.")
    if fulfilment == Order.Fulfilment.DELIVER and not delivery_address.strip():
        raise ShopError("Please give a delivery address.")

    with transaction.atomic():
        # Lock the rows in id order: two checkouts sharing products always queue, never deadlock
        products = {p.id: p for p in Product.objects.select_for_update().filter(id__in=items).order_by("id")}
        q = quote(items, fulfilment, discount_code, now, products=products)
        if q.problems:
            raise ShopError(" ".join(q.problems))
        if discount_code:
            dc = _usable_discount(discount_code, q.subtotal_cents, now, lock=True)
            dc.times_used += 1
            dc.save(update_fields=["times_used"])

        order = Order.objects.create(
            customer=customer, payment_method=payment_method, fulfilment=fulfilment, phone=phone.strip(),
            delivery_address=delivery_address.strip() if fulfilment == Order.Fulfilment.DELIVER else "",
            subtotal_cents=q.subtotal_cents, discount_code=q.discount_code, discount_cents=q.discount_cents,
            delivery_cents=q.delivery_cents, total_cents=q.total_cents, vat_cents=q.vat_cents,
            placed_at=now, pay_by=now + timedelta(days=settings.UNPAID_ORDER_DAYS[payment_method]))
        order.number = f"TW-{order.pk:06d}"
        order.save(update_fields=["number"])

        for line in q.lines:
            p = line.product
            OrderLine.objects.create(
                order=order, product=p, sku=p.sku, name=p.name, unit_price_cents=p.price_cents,
                quantity=line.quantity, vat_rate=p.vat_rate, discount_cents=line.discount_cents,
                line_total_cents=line.total_cents, vat_cents=line.vat_cents)
            _move_stock(p, -line.quantity, StockMovement.Reason.SALE, now, order=order)
        _event(order, "", S.AWAITING_PAYMENT, customer, now, f"{len(q.lines)} item line(s), {fmt(q.total_cents)}")
        return order


# ======================================================================
# After the order is placed
# ======================================================================

def mark_paid(staff, order, reference, now=None):
    reference = (reference or "").strip()
    if not reference:
        raise ShopError("Enter the payment reference (receipt or bank transfer number).")
    with transaction.atomic():
        order = _change(order, staff, S.AWAITING_PAYMENT, S.PAID, now, f"payment ref {reference}")
        order.paid_at, order.payment_reference = order._now, reference
        order.save()
        return order


def mark_packed(staff, order, now=None):
    with transaction.atomic():
        order = _change(order, staff, S.PAID, S.PACKED, now)
        order.packed_at = order._now
        order.save()
        return order


def mark_completed(staff, order, now=None):
    with transaction.atomic():
        how = "collected" if order.fulfilment == Order.Fulfilment.COLLECT else "delivered"
        order = _change(order, staff, S.PACKED, S.COMPLETED, now, how)
        order.completed_at = order._now
        order.save()
        return order


def cancel_order(user, order, reason, now=None):
    """Customers may cancel their own order until it's paid; staff until it's completed.
    Every item goes back into stock. A paid order is flagged for a refund."""
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ShopError("Please give a reason for cancelling.")
    with transaction.atomic():
        current = Order.objects.select_for_update().get(pk=order.pk)
        if not user.is_staff:
            if current.customer_id != user.id:
                raise NotAllowed("You can only cancel your own orders.")
            if current.status != S.AWAITING_PAYMENT:
                raise NotAllowed("This order has been paid, so please contact the shop to cancel it.")
        order = _change(current, user, [S.AWAITING_PAYMENT, S.PAID, S.PACKED], S.CANCELLED, now, reason)
        _return_stock(order, user)
        order.cancelled_at, order.cancel_reason = order._now, reason
        order.refund_due = order.paid_at is not None
        order.save()
        return order


def expire_unpaid_orders(now=None):
    """Cancel orders not paid by their deadline and put the stock back. Run once a day."""
    now = now or timezone.now()
    expired = []
    for order in Order.objects.filter(status=S.AWAITING_PAYMENT, pay_by__lt=now):
        with transaction.atomic():
            current = Order.objects.select_for_update().get(pk=order.pk)
            if current.status != S.AWAITING_PAYMENT:        # paid in the meantime
                continue
            current = _change(current, None, S.AWAITING_PAYMENT, S.CANCELLED, now, "not paid in time")
            _return_stock(current, None)
            current.cancelled_at, current.cancel_reason = now, "Not paid by the deadline"
            current.save()
            expired.append(current)
    return expired


# ======================================================================
# Stock
# ======================================================================

def restock(staff, product, quantity, note="", now=None):
    _require_staff(staff)
    if quantity <= 0:
        raise ShopError("Enter how many arrived (at least 1).")
    with transaction.atomic():
        p = Product.objects.select_for_update().get(pk=product.pk)
        return _move_stock(p, quantity, StockMovement.Reason.RESTOCK, now or timezone.now(), by=staff, note=note)


def correct_stock(staff, product, counted, note, now=None):
    """After a physical count: set stock to what's really on the shelf, recording the difference."""
    _require_staff(staff)
    if counted < 0:
        raise ShopError("A count can't be negative.")
    if len((note or "").strip()) < 3:
        raise ShopError("Say why the count differs (e.g. damaged, miscounted).")
    with transaction.atomic():
        p = Product.objects.select_for_update().get(pk=product.pk)
        if counted == p.stock:
            raise ShopError("That matches the current stock; nothing to correct.")
        return _move_stock(p, counted - p.stock, StockMovement.Reason.ADJUSTMENT, now or timezone.now(),
                           by=staff, note=note.strip())


# ======================================================================
# Helpers
# ======================================================================

def _move_stock(product, change, reason, now, order=None, by=None, note=""):
    """The only place stock changes. Caller holds the product's row lock."""
    product.stock += change
    if product.stock < 0:
        raise ShopError(f"Not enough {product.name} in stock.")
    product.save(update_fields=["stock"])
    return StockMovement.objects.create(product=product, change=change, balance_after=product.stock,
                                        reason=reason, order=order, by=by, note=note[:200], at=now)


def _return_stock(order, user):
    lines = list(order.lines.all())
    products = {p.id: p for p in Product.objects.select_for_update()
                .filter(id__in=[line.product_id for line in lines]).order_by("id")}
    for line in lines:
        _move_stock(products[line.product_id], line.quantity, StockMovement.Reason.RETURN, order._now,
                    order=order, by=user, note=f"{order.number} cancelled")


def _change(order, user, allowed_from, to, now, note=""):
    """Move an order to a new status, if the life cycle allows it, and record the step."""
    allowed_from = [allowed_from] if isinstance(allowed_from, str) else allowed_from
    if user is not None and to != S.CANCELLED:
        _require_staff(user)
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status not in allowed_from:
        raise ShopError(f"Order {order.number} is {order.get_status_display().lower()}, "
                        f"so it can't be marked {S(to).label.lower()}.")
    order._now = now or timezone.now()
    _event(order, order.status, to, user, order._now, note)
    order.status = to
    return order


def _event(order, from_status, to_status, user, now, note=""):
    OrderEvent.objects.create(order=order, from_status=from_status, to_status=to_status, by=user,
                              note=note[:200], at=now)


def _require_staff(user):
    if user is None or not user.is_staff:
        raise NotAllowed("Only shop staff can do that.")
