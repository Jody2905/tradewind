import pytest

from shop.money import allocate, fmt, percent_of, vat_included


@pytest.mark.parametrize("gross, rate, vat", [(1160, 16, 160), (11600, 16, 1600), (100, 16, 14), (850, 0, 0), (1, 16, 0)])
def test_vat_inside_a_price(gross, rate, vat):
    assert vat_included(gross, rate) == vat


def test_rounding_is_half_up():
    assert percent_of(1005, 10) == 101          # 100.5 -> 101, not "banker's" 100
    assert percent_of(1004, 10) == 100


@pytest.mark.parametrize("total, weights", [(100, [1, 1, 1]), (1, [5, 5]), (999, [2320, 850, 7500]),
                                            (0, [3, 4]), (7, [0, 0, 1])])
def test_allocation_always_adds_up(total, weights):
    shares = allocate(total, weights)
    assert sum(shares) == total
    assert all(s >= 0 for s in shares)


def test_allocation_is_proportional():
    assert allocate(100, [1, 1, 1]) == [34, 33, 33]
    assert allocate(1000, [3000, 1000]) == [750, 250]


def test_format():
    assert fmt(1234567) == "EC$12,345.67"
    assert fmt(5) == "EC$0.05"
    assert fmt(-250) == "-EC$2.50"
