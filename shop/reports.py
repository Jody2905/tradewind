"""Sales and VAT figures for a period.

What counts as a sale: an order PAID within the period that hasn't since been
cancelled. The payment date is the date that matters for VAT here (the "tax
point"), so a sale belongs to the day the money arrived, not the day the
order was placed.

Every figure is built from the frozen amounts on the orders and order lines,
so a report for last month never changes because a price changed today.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.db.models import Count, F, Sum
from django.utils import timezone

from .models import Order, OrderLine, Product
from .money import vat_included


@dataclass
class VatRow:
    rate: int
    label: str
    gross_cents: int        # what customers paid, VAT included
    vat_cents: int

    @property
    def net_cents(self):
        return self.gross_cents - self.vat_cents


@dataclass
class SalesReport:
    start: datetime
    end: datetime                           # exclusive
    orders: list
    days: list                              # (date, gross cents, order count), one per day, no gaps
    vat_rows: list
    top_products: list                      # (name, sku, quantity, gross cents)
    gross_cents: int = 0
    discount_cents: int = 0
    delivery_cents: int = 0
    vat_cents: int = 0
    refunds_due: list = field(default_factory=list)

    @property
    def net_cents(self):
        return self.gross_cents - self.vat_cents

    @property
    def order_count(self):
        return len(self.orders)

    @property
    def average_cents(self):
        return round(self.gross_cents / len(self.orders)) if self.orders else 0


def local_day_bounds(first_day, last_day):
    """[start of first_day, start of the day after last_day) in the shop's time zone."""
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(first_day, time.min), tz),
            timezone.make_aware(datetime.combine(last_day + timedelta(days=1), time.min), tz))


def sales_report(first_day, last_day):
    start, end = local_day_bounds(first_day, last_day)
    orders = list(Order.objects.filter(paid_at__gte=start, paid_at__lt=end)
                  .exclude(status=Order.Status.CANCELLED).select_related("customer").order_by("paid_at"))
    ids = [o.id for o in orders]

    per_day = defaultdict(lambda: [0, 0])
    for o in orders:
        day = timezone.localtime(o.paid_at).date()
        per_day[day][0] += o.total_cents
        per_day[day][1] += 1
    days, d = [], first_day
    while d <= last_day:
        days.append((d, per_day[d][0], per_day[d][1]))
        d += timedelta(days=1)

    lines = OrderLine.objects.filter(order_id__in=ids)
    by_rate = {r["vat_rate"]: r for r in lines.values("vat_rate").annotate(
        gross=Sum("line_total_cents"), vat=Sum("vat_cents"))}
    delivery_gross = sum(o.delivery_cents for o in orders)
    delivery_vat = sum(vat_included(o.delivery_cents, 16) for o in orders)
    vat_rows = [
        VatRow(16, "Goods at 16%", by_rate.get(16, {}).get("gross") or 0, by_rate.get(16, {}).get("vat") or 0),
        VatRow(16, "Delivery at 16%", delivery_gross, delivery_vat),
        VatRow(0, "Zero-rated goods", by_rate.get(0, {}).get("gross") or 0, 0),
    ]
    top = [(r["name"], r["sku"], r["qty"], r["gross"]) for r in lines.values("sku", "name").annotate(
        qty=Sum("quantity"), gross=Sum("line_total_cents")).order_by("-gross", "sku")[:10]]

    refunds = list(Order.objects.filter(refund_due=True, cancelled_at__gte=start, cancelled_at__lt=end))
    return SalesReport(
        start=start, end=end, orders=orders, days=days, vat_rows=vat_rows, top_products=top,
        gross_cents=sum(o.total_cents for o in orders), discount_cents=sum(o.discount_cents for o in orders),
        delivery_cents=delivery_gross, vat_cents=sum(o.vat_cents for o in orders), refunds_due=refunds)


def dashboard_counts(now=None):
    now = now or timezone.now()
    status = dict(Order.objects.values_list("status").annotate(n=Count("id")))
    return {
        "awaiting": status.get(Order.Status.AWAITING_PAYMENT, 0),
        "overdue": Order.objects.filter(status=Order.Status.AWAITING_PAYMENT, pay_by__lt=now).count(),
        "to_pack": status.get(Order.Status.PAID, 0),
        "ready": status.get(Order.Status.PACKED, 0),
        "low_stock": Product.objects.filter(active=True, stock__lte=F("low_stock_level")).count(),
        "refunds_due": Order.objects.filter(refund_due=True).count(),
    }
