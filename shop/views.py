"""The shop pages customers use.

Views stay thin: they read the request, call the rules in services.py and
show the result. Anything that changes data is POST-only and CSRF-protected
(Django's middleware). Customers can only ever see their own orders; anyone
else's order number gives "not found", which doesn't even confirm it exists.
"""

import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import basket, services
from .forms import CancelForm, CheckoutForm, SignupForm
from .models import Category, Order, Product
from .services import MAX_PER_LINE, ShopError

PER_PAGE = 12


# ---- Browsing --------------------------------------------------------------------

def catalogue(request):
    products = Product.objects.filter(active=True).select_related("category")
    category = None
    if slug := request.GET.get("category"):
        category = get_object_or_404(Category, slug=slug)
        products = products.filter(category=category)
    query = request.GET.get("q", "").strip()[:80]
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(sku__iexact=query))
    page = Paginator(products.order_by("name"), PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "shop/catalogue.html", {
        "page": page, "categories": Category.objects.all(), "category": category, "query": query})


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.select_related("category"), slug=slug, active=True)
    in_basket = basket.items(request.session).get(product.id, 0)
    return render(request, "shop/product.html", {
        "product": product, "in_basket": in_basket,
        "max_qty": max(0, min(product.stock, MAX_PER_LINE) - in_basket)})


# ---- The basket -----------------------------------------------------------------

@require_POST
def basket_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, active=True)
    qty = _int(request.POST.get("quantity"), 1)
    already = basket.items(request.session).get(product.id, 0)
    if qty < 1:
        messages.error(request, "Choose a quantity of at least 1.")
    elif already + qty > product.stock:
        messages.error(request, f"Sorry, only {product.stock} {product.name} in stock"
                                + (f" and you already have {already} in your basket." if already else "."))
    else:
        basket.add(request.session, product.id, qty)
        messages.success(request, f"Added {qty} × {product.name} to your basket.")
    return redirect("product", slug=product.slug)


def basket_view(request):
    fulfilment = request.GET.get("fulfilment", Order.Fulfilment.COLLECT)
    q = services.quote(basket.items(request.session), fulfilment, basket.discount_code(request.session))
    return render(request, "shop/basket.html", {"q": q, "fulfilment": fulfilment,
                                                "free_from": settings.FREE_DELIVERY_FROM_CENTS,
                                                "delivery_fee": settings.DELIVERY_FEE_CENTS})


@require_POST
def basket_update(request):
    for key, value in request.POST.items():
        if key.startswith("qty_"):
            basket.set_quantity(request.session, _int(key[4:], 0), _int(value, 0))
    if "remove" in request.POST:
        basket.set_quantity(request.session, _int(request.POST["remove"], 0), 0)
    messages.success(request, "Basket updated.")
    return redirect("basket")


@require_POST
def basket_discount(request):
    code = request.POST.get("code", "").strip()
    if "remove" in request.POST or not code:
        basket.set_discount_code(request.session, "")
        messages.success(request, "Discount code removed.")
        return redirect("basket")
    basket.set_discount_code(request.session, code)
    q = services.quote(basket.items(request.session), discount_code=code)
    if q.discount_code:
        messages.success(request, f"Code {q.discount_code} applied: you save {q.discount}.")
    else:
        basket.set_discount_code(request.session, "")
        messages.error(request, next((p for p in q.problems if "code" in p.lower()), "That code can't be used."))
    return redirect("basket")


# ---- Checkout -----------------------------------------------------------------------

@login_required
def checkout(request):
    items = basket.items(request.session)
    if not items:
        messages.info(request, "Your basket is empty.")
        return redirect("catalogue")

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        fulfilment = request.POST.get("fulfilment", Order.Fulfilment.COLLECT)
        if fulfilment not in Order.Fulfilment.values:
            fulfilment = Order.Fulfilment.COLLECT
        # A one-time token: a double click or a refresh can't place the same order twice
        expected = request.session.get("checkout_token")
        if not expected or not secrets.compare_digest(request.POST.get("token", ""), expected):
            messages.info(request, "That order was already placed. It's below.")
            return redirect("my_orders")
        if form.is_valid():
            d = form.cleaned_data
            try:
                order = services.place_order(
                    request.user, items, d["payment_method"], d["fulfilment"], d["phone"],
                    delivery_address=d["delivery_address"], discount_code=basket.discount_code(request.session))
            except ShopError as e:
                messages.error(request, str(e))
            else:
                request.session.pop("checkout_token", None)
                basket.clear(request.session)
                messages.success(request, f"Thank you! Your order {order.number} is placed.")
                return redirect("order", number=order.number)
    else:
        fulfilment = request.GET.get("fulfilment", Order.Fulfilment.COLLECT)
        if fulfilment not in Order.Fulfilment.values:
            fulfilment = Order.Fulfilment.COLLECT
        request.session["checkout_token"] = secrets.token_urlsafe(16)
        last = request.user.orders.order_by("-placed_at").first()
        form = CheckoutForm(initial={"token": request.session["checkout_token"], "fulfilment": fulfilment,
                                     "phone": last.phone if last else "",
                                     "delivery_address": last.delivery_address if last else ""})
    q = services.quote(items, fulfilment, basket.discount_code(request.session))
    return render(request, "shop/checkout.html", {"form": form, "q": q, "fulfilment": fulfilment})


# ---- Orders -------------------------------------------------------------------------

@login_required
def my_orders(request):
    return render(request, "shop/my_orders.html",
                  {"orders": request.user.orders.prefetch_related("lines").order_by("-placed_at")})


@login_required
def order_detail(request, number):
    order = _own_order(request, number)
    return render(request, "shop/order.html", {
        "order": order, "lines": order.lines.all(), "events": order.events.all(),
        "bank": settings.BANK_DETAILS, "can_cancel": order.status == Order.Status.AWAITING_PAYMENT,
        "cancel_form": CancelForm()})


@login_required
@require_POST
def order_cancel(request, number):
    order = _own_order(request, number)
    form = CancelForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please say why you're cancelling (a few words).")
        return redirect("order", number=number)
    try:
        services.cancel_order(request.user, order, form.cleaned_data["reason"])
        messages.success(request, f"Order {order.number} is cancelled.")
    except ShopError as e:
        messages.error(request, str(e))
    return redirect("order", number=number)


# ---- Accounts -------------------------------------------------------------------------

def signup(request):
    if request.user.is_authenticated:
        return redirect("catalogue")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Welcome, {user.first_name}! Your account is ready.")
        return redirect(_safe_next(request) or "catalogue")
    return render(request, "registration/signup.html", {"form": form})


# ---- Helpers ---------------------------------------------------------------------------

def _own_order(request, number):
    order = Order.objects.filter(number=number).first()
    if order is None or order.customer_id != request.user.id:
        raise Http404("No such order")
    return order


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_next(request):
    from django.utils.http import url_has_allowed_host_and_scheme
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return nxt
    return None
