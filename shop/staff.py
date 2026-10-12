"""The staff side of the shop: orders to process, stock, and reports.

Only accounts marked as staff can open these pages. Anyone else, including a
logged-in customer, gets "not found", so the pages don't even reveal they exist.
Every action goes through services.py, which checks staff status again.
"""

from datetime import date, timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db.models import F, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import exports, reports, services
from .models import Order, Product, StockMovement
from .services import ShopError


def staff_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_staff:
            raise Http404()
        return view(request, *args, **kwargs)
    return wrapped


def _attempt(request, action, success):
    try:
        result = action()
        messages.success(request, success(result) if callable(success) else success)
    except ShopError as e:
        messages.error(request, str(e))


# ---- Dashboard -------------------------------------------------------------------------

@staff_only
def dashboard(request):
    today = timezone.localdate()
    report = reports.sales_report(today - timedelta(days=6), today)
    return render(request, "staff/dashboard.html", {
        "counts": reports.dashboard_counts(), "week": report,
        "peak": max((g for _, g, _ in report.days), default=0),
        "to_pack": Order.objects.filter(status=Order.Status.PAID).select_related("customer").order_by("paid_at")[:8],
        "low": Product.objects.filter(active=True, stock__lte=F("low_stock_level")).order_by("stock", "name")[:8]})


# ---- Orders ----------------------------------------------------------------------------

@staff_only
def order_list(request):
    status = request.GET.get("status", "")
    orders = Order.objects.select_related("customer").order_by("-placed_at")
    if status == "overdue":
        orders = orders.filter(status=Order.Status.AWAITING_PAYMENT, pay_by__lt=timezone.now())
    elif status == "refund_due":
        orders = orders.filter(refund_due=True)
    elif status in Order.Status.values:
        orders = orders.filter(status=status)
    q = request.GET.get("q", "").strip()[:80]
    if q:
        orders = orders.filter(Q(number__iexact=q) | Q(customer__email__icontains=q) | Q(customer__last_name__icontains=q)
                               | Q(phone__icontains=q))
    return render(request, "staff/orders.html", {
        "orders": orders[:200], "status": status, "q": q, "statuses": Order.Status.choices,
        "now": timezone.now()})


@staff_only
def order_detail(request, number):
    order = get_object_or_404(Order.objects.select_related("customer"), number=number)
    return render(request, "staff/order.html", {"order": order, "lines": order.lines.all(),
                                                 "events": order.events.select_related("by"), "now": timezone.now()})


@staff_only
def packing_slip(request, number):
    order = get_object_or_404(Order, number=number)
    if order.status not in (Order.Status.PAID, Order.Status.PACKED):
        raise Http404()
    return render(request, "staff/slip.html", {"order": order, "lines": order.lines.all()})


@staff_only
@require_POST
def order_action(request, number, action):
    order = get_object_or_404(Order, number=number)
    user, post = request.user, request.POST
    if action == "paid":
        _attempt(request, lambda: services.mark_paid(user, order, post.get("reference")),
                 f"{order.number}: payment recorded. It's now in the packing queue.")
    elif action == "packed":
        _attempt(request, lambda: services.mark_packed(user, order), f"{order.number} is packed.")
    elif action == "completed":
        _attempt(request, lambda: services.mark_completed(user, order), f"{order.number} is complete.")
    elif action == "cancel":
        _attempt(request, lambda: services.cancel_order(user, order, post.get("reason")),
                 lambda o: f"{o.number} cancelled and stock returned." + (" A refund is due." if o.refund_due else ""))
    elif action == "refund":
        _attempt(request, lambda: services.record_refund(user, order, post.get("reference")),
                 f"Refund on {order.number} recorded.")
    else:
        raise Http404()
    return redirect("staff_order", number=order.number)


@staff_only
@require_POST
def expire_now(request):
    expired = services.expire_unpaid_orders()
    messages.success(request, f"{len(expired)} overdue unpaid order(s) cancelled and their stock released."
                     if expired else "No overdue unpaid orders.")
    return redirect("staff_orders")


# ---- Stock -----------------------------------------------------------------------------

@staff_only
def stock(request):
    products = Product.objects.select_related("category").order_by("name")
    if request.GET.get("low"):
        products = products.filter(stock__lte=F("low_stock_level"), active=True)
    return render(request, "staff/stock.html", {"products": products, "low_only": bool(request.GET.get("low"))})


@staff_only
def stock_history(request, sku):
    product = get_object_or_404(Product, sku=sku)
    return render(request, "staff/stock_history.html", {
        "product": product, "movements": product.movements.select_related("order", "by")[:200]})


@staff_only
@require_POST
def stock_action(request, sku, action):
    product = get_object_or_404(Product, sku=sku)
    note = request.POST.get("note", "")
    try:
        number = int(request.POST.get("quantity", ""))
    except ValueError:
        messages.error(request, "Enter a whole number.")
        return redirect("staff_stock_history", sku=sku)
    if action == "restock":
        _attempt(request, lambda: services.restock(request.user, product, number, note),
                 lambda m: f"Received {number}. {product.name} now has {m.balance_after} in stock.")
    elif action == "count":
        _attempt(request, lambda: services.correct_stock(request.user, product, number, note),
                 lambda m: f"Stock corrected by {m.change:+d} to {m.balance_after}.")
    else:
        raise Http404()
    return redirect("staff_stock_history", sku=sku)


# ---- Reports ---------------------------------------------------------------------------

def _period(request):
    today = timezone.localdate()
    try:
        first = date.fromisoformat(request.GET.get("from", ""))
        last = date.fromisoformat(request.GET.get("to", ""))
    except ValueError:
        first, last = today.replace(day=1), today            # default: this month so far
    if last < first:
        first, last = last, first
    return first, min(last, first + timedelta(days=366))     # at most a year at a time


@staff_only
def sales(request):
    first, last = _period(request)
    report = reports.sales_report(first, last)
    return render(request, "staff/sales.html", {
        "r": report, "first": first, "last": last, "peak": max((g for _, g, _ in report.days), default=0)})


@staff_only
def sales_xlsx(request):
    first, last = _period(request)
    data = exports.sales_workbook(reports.sales_report(first, last), settings.SHOP_NAME)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="tradewind-sales-{first}-to-{last}.xlsx"'
    return response
