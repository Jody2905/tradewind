"""The basket lives in the visitor's session, so it works before logging in.

Django keeps the session's contents when someone logs in (it only changes the
session's ID, to stop session-fixation attacks), so the basket carries over.

Stored as {"<product id>": quantity}. Nothing here is trusted for prices or
stock: checkout re-prices and re-checks everything from the database.
"""

from .services import MAX_PER_LINE

KEY = "basket"
CODE_KEY = "discount_code"


def items(session):
    """{product_id: quantity}, ignoring anything malformed."""
    clean = {}
    for pid, qty in session.get(KEY, {}).items():
        try:
            pid, qty = int(pid), int(qty)
        except (TypeError, ValueError):
            continue
        if 0 < qty <= MAX_PER_LINE:
            clean[pid] = qty
    return clean


def count(session):
    return sum(items(session).values())


def add(session, product_id, quantity):
    basket = items(session)
    basket[product_id] = min(basket.get(product_id, 0) + quantity, MAX_PER_LINE)
    _save(session, basket)


def set_quantity(session, product_id, quantity):
    basket = items(session)
    if quantity <= 0:
        basket.pop(product_id, None)
    else:
        basket[product_id] = min(quantity, MAX_PER_LINE)
    _save(session, basket)


def clear(session):
    session.pop(KEY, None)
    session.pop(CODE_KEY, None)


def discount_code(session):
    return session.get(CODE_KEY, "")


def set_discount_code(session, code):
    if code:
        session[CODE_KEY] = code.strip().upper()[:30]
    else:
        session.pop(CODE_KEY, None)


def _save(session, basket):
    session[KEY] = {str(k): v for k, v in basket.items()}
