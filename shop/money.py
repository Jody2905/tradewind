"""Money arithmetic.

Every amount is a whole number of cents (an int), never a float. Shop prices
include VAT, as customers see them on the shelf. The VAT inside a price is
worked out per order line:

    VAT = price x rate / (100 + rate)       e.g. EC$11.60 at 16% contains EC$1.60

Rounding is "half up" to the nearest cent, done once per line and never on a
running total, so the lines always add up to the totals printed on the order.
"""

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value):
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def vat_included(gross_cents, rate_percent):
    """The VAT already contained in a VAT-inclusive amount."""
    if rate_percent == 0:
        return 0
    return round_half_up(Decimal(gross_cents) * rate_percent / (100 + rate_percent))


def percent_of(cents, percent):
    return round_half_up(Decimal(cents) * percent / 100)


def allocate(total, weights):
    """Split `total` cents across lines in proportion to `weights`, exactly.

    Uses the largest-remainder method so the pieces always add up to the
    total: allocate(100, [1, 1, 1]) -> [34, 33, 33], never [33, 33, 33].
    """
    weight_sum = sum(weights)
    if total == 0 or weight_sum == 0:
        return [0] * len(weights)
    exact = [Decimal(total) * w / weight_sum for w in weights]
    shares = [int(x) for x in exact]                    # round everything down first
    leftover = total - sum(shares)
    by_remainder = sorted(range(len(weights)), key=lambda i: (exact[i] - shares[i], -i), reverse=True)
    for i in by_remainder[:leftover]:                   # then give the spare cents to the biggest remainders
        shares[i] += 1
    return shares


def fmt(cents, symbol="EC$"):
    """1234567 -> 'EC$12,345.67'"""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{symbol}{cents // 100:,}.{cents % 100:02d}"
