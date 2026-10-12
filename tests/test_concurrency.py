"""Ten customers press "Place order" at the same instant for the last 3 baskets."""

import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from shop import services
from shop.models import Order, Product
from shop.services import ShopError

from .conftest import NOW


@pytest.mark.django_db(transaction=True)          # real commits, so the threads see each other's work
def test_last_items_are_never_oversold(products):
    basket = products["basket"]                    # 3 in stock
    buyers = [get_user_model().objects.create_user(f"buyer{i}", f"b{i}@example.test", "x") for i in range(10)]
    start = threading.Barrier(len(buyers))
    outcomes = []

    def buy(user):
        start.wait()
        try:
            services.place_order(user, {basket.id: 1}, "collection", "collect", "784-555-0101", now=NOW)
            outcomes.append("bought")
        except ShopError:
            outcomes.append("sold out")
        finally:
            connection.close()                     # each thread has its own database connection

    threads = [threading.Thread(target=buy, args=(u,)) for u in buyers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("bought") == 3
    assert outcomes.count("sold out") == 7
    assert Product.objects.get(pk=basket.pk).stock == 0
    assert Order.objects.count() == 3
