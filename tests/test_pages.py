"""The shop pages: browsing, the basket, checkout, orders, accounts and security."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from shop import services
from shop.models import Order, Product

from .conftest import PASSWORD, items


@pytest.fixture
def shopper(client, customer):
    client.force_login(customer)
    return client


def add(client, product, qty=1):
    return client.post(reverse("basket_add", args=[product.id]), {"quantity": qty})


def checkout_page(client, fulfilment="collect"):
    r = client.get(reverse("checkout") + f"?fulfilment={fulfilment}")
    token = re.search(r'name="token" value="([^"]+)"', r.content.decode()).group(1)
    return r, token


def place(client, token, **extra):
    data = {"token": token, "fulfilment": "collect", "phone": "784-555-0101", "payment_method": "collection"}
    data.update(extra)
    return client.post(reverse("checkout"), data)


# ---- Browsing -----------------------------------------------------------------------

def test_catalogue_lists_active_products_with_stock_labels(client, products):
    Product.objects.filter(sku="NT-02").update(active=False)
    Product.objects.filter(sku="BK-03").update(stock=0)
    html = client.get(reverse("catalogue")).content.decode()
    assert "Scotch Bonnet Hot Sauce" in html and "EC$11.60" in html
    assert "Whole Nutmeg" not in html                          # withdrawn products are hidden
    assert "Out of stock" in html


def test_search_and_category_filter(client, products):
    html = client.get(reverse("catalogue"), {"q": "palm"}).content.decode()
    assert "Woven Palm Basket" in html and "Hot Sauce" not in html and "1 result" in html
    html = client.get(reverse("catalogue"), {"category": "pantry"}).content.decode()
    assert "Hot Sauce" in html and "Woven Palm Basket" not in html
    assert client.get(reverse("catalogue"), {"category": "no-such"}).status_code == 404


def test_product_page(client, products):
    html = client.get(reverse("product", args=["bk-03"])).content.decode()
    assert "Only 3 left" in html and "Includes 16% VAT" in html
    assert "VAT-free" in client.get(reverse("product", args=["nt-02"])).content.decode()
    Product.objects.filter(sku="BK-03").update(active=False)
    assert client.get(reverse("product", args=["bk-03"])).status_code == 404


# ---- The basket -----------------------------------------------------------------------

def test_basket_works_without_logging_in(client, products):
    add(client, products["hot_sauce"], 2)
    add(client, products["nutmeg"])
    html = client.get(reverse("basket")).content.decode()
    assert "EC$31.70" in html and "Includes VAT" in html and "EC$3.20" in html


def test_cannot_put_more_in_the_basket_than_is_in_stock(client, products):
    add(client, products["basket"], 2)
    r = add(client, products["basket"], 2)
    assert "only 3 Woven Palm Basket in stock and you already have 2" in r.wsgi_request._messages._queued_messages[0].message
    assert client.session["basket"] == {str(products["basket"].id): 2}


def test_update_and_remove(client, products):
    add(client, products["hot_sauce"], 2)
    add(client, products["nutmeg"])
    client.post(reverse("basket_update"), {f"qty_{products['hot_sauce'].id}": 5})
    assert client.session["basket"][str(products["hot_sauce"].id)] == 5
    client.post(reverse("basket_update"), {"remove": products["nutmeg"].id})
    assert str(products["nutmeg"].id) not in client.session["basket"]


def test_discount_code_in_basket(client, products, code):
    add(client, products["basket"])
    r = client.post(reverse("basket_discount"), {"code": "welcome10"}, follow=True)
    assert "you save EC$7.50" in r.content.decode()
    r = client.post(reverse("basket_discount"), {"code": "NOPE"}, follow=True)
    assert "isn&#x27;t valid" in r.content.decode() and "basket" in client.session


def test_basket_ignores_tampered_session_values(client, products):
    session = client.session
    session["basket"] = {str(products["hot_sauce"].id): "lots", "x": 1, str(products["nutmeg"].id): -4,
                         str(products["basket"].id): 1}
    session.save()
    html = client.get(reverse("basket")).content.decode()
    assert "Woven Palm Basket" in html and "Hot Sauce" not in html and "Nutmeg" not in html


# ---- Checkout -------------------------------------------------------------------------

def test_checkout_needs_login_and_basket_survives_login(client, customer, products):
    add(client, products["hot_sauce"], 2)
    r = client.get(reverse("checkout"))
    assert r.status_code == 302 and reverse("login") in r["Location"]
    r = client.post(reverse("login"), {"username": "KERRY@example.test", "password": PASSWORD})
    assert r.status_code == 302                                 # email login is case-insensitive
    assert client.session["basket"] == {str(products["hot_sauce"].id): 2}


def test_place_order_end_to_end(shopper, customer, products):
    add(shopper, products["hot_sauce"], 2)
    _, token = checkout_page(shopper)
    r = place(shopper, token)
    order = Order.objects.get()
    assert r.status_code == 302 and r["Location"] == reverse("order", args=[order.number])
    assert order.customer == customer and order.total_cents == 2320
    assert "basket" not in shopper.session                     # basket emptied
    html = shopper.get(r["Location"]).content.decode()
    assert "Pay when you collect" in html and order.number in html


def test_double_submit_places_one_order(shopper, products):
    add(shopper, products["hot_sauce"])
    _, token = checkout_page(shopper)
    place(shopper, token)
    add(shopper, products["hot_sauce"])                         # even with something new in the basket
    r = place(shopper, token)                                    # the same form sent again
    assert Order.objects.count() == 1
    assert r["Location"] == reverse("my_orders")


def test_bank_transfer_shows_bank_details(shopper, products):
    add(shopper, products["basket"])
    _, token = checkout_page(shopper)
    r = place(shopper, token, payment_method="bank_transfer")
    html = shopper.get(r["Location"]).content.decode()
    assert "Please pay by bank transfer" in html and "not a real account" in html


def test_delivery_needs_address_and_charges_fee(shopper, products):
    add(shopper, products["hot_sauce"])
    r, token = checkout_page(shopper, "deliver")
    assert "EC$25.00" in r.content.decode() and "EC$36.60" in r.content.decode()
    r = place(shopper, token, fulfilment="deliver")
    assert r.status_code == 200 and "Please give a delivery address" in r.content.decode()
    r = place(shopper, token, fulfilment="deliver", delivery_address="Bay Street")
    assert Order.objects.get().delivery_cents == 2500


def test_stock_change_during_checkout_is_caught(shopper, products):
    add(shopper, products["basket"], 3)
    _, token = checkout_page(shopper)
    Product.objects.filter(sku="BK-03").update(stock=1)          # someone else bought two meanwhile
    r = place(shopper, token)
    assert r.status_code == 200 and "Only 1 Woven Palm Basket left" in r.content.decode()
    assert not Order.objects.exists()


def test_empty_basket_checkout_goes_back_to_shop(shopper):
    assert shopper.get(reverse("checkout"))["Location"] == reverse("catalogue")


# ---- Orders -------------------------------------------------------------------------

@pytest.fixture
def order(customer, products):
    return services.place_order(customer, items(products, hot_sauce=1), "collection", "collect", "784-555-0101")


def test_my_orders_lists_only_mine(shopper, other_customer, products, order):
    services.place_order(other_customer, items(products, nutmeg=1), "collection", "collect", "784-555-0102")
    html = shopper.get(reverse("my_orders")).content.decode()
    other = Order.objects.exclude(pk=order.pk).get()
    assert order.number in html and other.number not in html


def test_cannot_see_someone_elses_order(client, other_customer, order):
    client.force_login(other_customer)
    assert client.get(reverse("order", args=[order.number])).status_code == 404
    assert client.post(reverse("order_cancel", args=[order.number]), {"reason": "not mine"}).status_code == 404
    assert Order.objects.get().status == "awaiting_payment"


def test_customer_cancels_unpaid_order(shopper, order):
    r = shopper.post(reverse("order_cancel", args=[order.number]), {"reason": "wrong item"}, follow=True)
    assert "is cancelled" in r.content.decode()
    assert Product.objects.get(sku="HS-01").stock == 20


def test_cancel_is_post_only(shopper, order):
    assert shopper.get(reverse("order_cancel", args=[order.number])).status_code == 405


# ---- Accounts and security ---------------------------------------------------------------

@pytest.mark.django_db
def test_sign_up_uses_email_and_strong_password(client):
    r = client.post(reverse("signup"), {"first_name": "Nadia", "last_name": "Pope", "email": "Nadia@Example.test",
                                        "password1": "password123", "password2": "password123"})
    assert r.status_code == 200 and "too common" in r.content.decode()
    r = client.post(reverse("signup"), {"first_name": "Nadia", "last_name": "Pope", "email": "Nadia@Example.test",
                                        "password1": PASSWORD, "password2": PASSWORD})
    assert r.status_code == 302
    user = get_user_model().objects.get(email="nadia@example.test")
    assert user.username == "nadia@example.test" and not user.is_staff


def test_duplicate_email_refused(client, customer):
    get_user_model().objects.create_user("made-in-admin", "staffmade@example.test", PASSWORD)
    r = client.post(reverse("signup"), {"first_name": "S", "last_name": "M", "email": "StaffMade@example.test",
                                        "password1": PASSWORD, "password2": PASSWORD})
    assert "already an account" in r.content.decode()      # caught via the email field, not the username
    r = client.post(reverse("signup"), {"first_name": "K", "last_name": "B", "email": "KERRY@example.test",
                                        "password1": PASSWORD, "password2": PASSWORD})
    assert "already an account" in r.content.decode()


@pytest.mark.django_db
def test_open_redirect_after_signup_is_blocked(client):
    r = client.post(reverse("signup") + "?next=https://evil.example/", {
        "first_name": "N", "last_name": "P", "email": "n@example.test", "password1": PASSWORD,
        "password2": PASSWORD, "next": "https://evil.example/"})
    assert r["Location"] == reverse("catalogue")


def test_forms_need_csrf_token(products):
    from django.test import Client
    strict = Client(enforce_csrf_checks=True)
    assert strict.post(reverse("basket_add", args=[products["hot_sauce"].id]), {"quantity": 1}).status_code == 403


def test_security_headers(shopper):
    r = shopper.get(reverse("catalogue"))
    assert "default-src 'self'" in r["Content-Security-Policy"]
    assert r["X-Frame-Options"] == "DENY" and r["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in r["Cache-Control"]


def test_search_text_is_escaped(client, products):
    html = client.get(reverse("catalogue"), {"q": "<script>alert(1)</script>"}).content.decode()
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
