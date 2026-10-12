from django.conf import settings

from . import basket


def shop(request):
    """Available on every page: the basket count and the shop's name."""
    return {"basket_count": basket.count(request.session), "SHOP_NAME": settings.SHOP_NAME}
