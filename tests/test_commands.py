from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from shop.models import Order, Product, StockMovement


def run(*args):
    out = StringIO()
    call_command(*args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_walkthrough_refuses_what_it_should_and_saves_nothing():
    text = run("shop_demo")
    assert "!!" not in text and text.count("REFUSED") == 3
    assert "total EC$96.03, of which VAT EC$12.19" in text
    assert not Product.objects.exists() and not Order.objects.exists()


@pytest.mark.django_db
def test_seed_demo_builds_a_consistent_shop():
    text = run("seed_demo")
    assert "Added 17 products" in text
    for p in Product.objects.all():                    # opening stock went through the ledger
        assert p.stock == sum(m.change for m in StockMovement.objects.filter(product=p))
    with pytest.raises(CommandError, match="already has products"):
        run("seed_demo")


@pytest.mark.django_db
def test_expire_command():
    assert "0 unpaid order(s) cancelled" in run("expire_unpaid_orders")


@pytest.mark.django_db
def test_migrations_match_the_models():
    """Fails if someone changes models.py and forgets to create a migration."""
    call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())
