from datetime import datetime, timedelta, timezone as tz

import pytest
from django.contrib.auth import get_user_model

from shop.models import Category, DiscountCode, Product

NOW = datetime(2026, 11, 2, 14, 0, tzinfo=tz.utc)
PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fast_passwords(settings):
    """Real password hashing is slow on purpose; tests don't need that."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user("kerry@example.test", "kerry@example.test", PASSWORD, first_name="Kerry")


@pytest.fixture
def other_customer(db):
    return get_user_model().objects.create_user("marlon@example.test", "marlon@example.test", PASSWORD, first_name="Marlon")


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_user("shane@tradewind.test", "shane@tradewind.test", PASSWORD, is_staff=True)


@pytest.fixture
def products(db):
    food = Category.objects.create(name="Pantry", slug="pantry")
    crafts = Category.objects.create(name="Crafts", slug="crafts")

    def make(sku, name, cat, price, stock, vat=16):
        return Product.objects.create(sku=sku, name=name, slug=sku.lower(), category=cat, price_cents=price,
                                      stock=stock, vat_rate=vat)
    return {
        "hot_sauce": make("HS-01", "Scotch Bonnet Hot Sauce", food, 1160, 20),      # EC$11.60 incl. 16% VAT
        "nutmeg": make("NT-02", "Whole Nutmeg 100g", food, 850, 10, vat=0),         # zero-rated
        "basket": make("BK-03", "Woven Palm Basket", crafts, 7500, 3),
    }


@pytest.fixture
def code(db):
    return DiscountCode.objects.create(code="WELCOME10", percent_off=10, valid_from=NOW - timedelta(days=30),
                                       valid_until=NOW + timedelta(days=30))


def items(products, **quantities):
    """items(products, hot_sauce=2) -> {id: 2}"""
    return {products[name].id: qty for name, qty in quantities.items()}
