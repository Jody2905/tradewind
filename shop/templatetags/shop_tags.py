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


@register.filter
def bar_height(value, peak):
    """A bar's height as a CSS step (0, 5, 10 ... 100). Any non-zero value shows at least a sliver."""
    if not value or not peak:
        return 0
    return max(5, round(100 * value / peak / 5) * 5)
