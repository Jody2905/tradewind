from django import template

from shop.money import fmt

register = template.Library()


@register.filter
def money(cents):
    """{{ product.price_cents|money }} -> EC$11.60"""
    return fmt(int(cents or 0))


@register.filter
def initials(name):
    """'Woven Palm Basket' -> 'WP' (used on the product artwork)."""
    words = [w for w in name.replace(",", " ").split() if w[:1].isalpha()]
    return "".join(w[0] for w in words[:2]).upper()


@register.simple_tag
def stock_label(product):
    if product.stock == 0:
        return "Out of stock"
    if product.low_on_stock:
        return f"Only {product.stock} left"
    return "In stock"
