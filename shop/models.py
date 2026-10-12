"""Tradewind's tables.

Key rules are enforced by the database itself (CHECK and UNIQUE constraints),
not just by Python code, so even a bug or a hand-written query can't create
negative stock, a zero-quantity order line or a duplicate SKU.

All money is in whole cents and includes VAT.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from .money import fmt


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    class Vat(models.IntegerChoices):
        STANDARD = 16, "Standard (16%)"
        ZERO = 0, "Zero-rated (0%)"

    sku = models.CharField("SKU", max_length=30, unique=True)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    description = models.TextField(blank=True)
    price_cents = models.PositiveIntegerField(help_text="Shelf price in cents, VAT included")
    vat_rate = models.PositiveSmallIntegerField(choices=Vat.choices, default=Vat.STANDARD)
    stock = models.IntegerField(default=0)
    low_stock_level = models.PositiveIntegerField(default=5)
    active = models.BooleanField(default=True, help_text="Untick to hide it from the shop without deleting it")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(stock__gte=0), name="stock_never_negative"),
            models.CheckConstraint(condition=Q(price_cents__gt=0), name="price_positive"),
            models.CheckConstraint(condition=Q(vat_rate__in=[0, 16]), name="known_vat_rate"),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def price(self):
        return fmt(self.price_cents)

    @property
    def low_on_stock(self):
        return self.stock <= self.low_stock_level


class StockMovement(models.Model):
    """Every change to stock, ever. The product's stock is always the sum of these."""

    class Reason(models.TextChoices):
        RESTOCK = "restock", "Delivery received"
        SALE = "sale", "Sold"
        RETURN = "return", "Returned to stock (order cancelled)"
        ADJUSTMENT = "adjustment", "Stock count correction"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    change = models.IntegerField()
    balance_after = models.IntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    order = models.ForeignKey("Order", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    note = models.CharField(max_length=200, blank=True)
    at = models.DateTimeField()

    class Meta:
        ordering = ["-at", "-id"]
        constraints = [
            models.CheckConstraint(condition=~Q(change=0), name="movement_not_zero"),
            models.CheckConstraint(condition=Q(balance_after__gte=0), name="balance_never_negative"),
        ]


class DiscountCode(models.Model):
    code = models.CharField(max_length=30, unique=True, help_text="Stored in capitals; customers can type any case")
    percent_off = models.PositiveSmallIntegerField()
    min_subtotal_cents = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Blank = unlimited")
    times_used = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(percent_off__gte=1, percent_off__lte=90), name="sensible_discount"),
            models.CheckConstraint(condition=Q(valid_until__gt=F("valid_from")), name="valid_period"),
            models.CheckConstraint(condition=Q(max_uses__isnull=True) | Q(times_used__lte=F("max_uses")),
                                   name="not_overused"),
        ]

    def __str__(self):
        return f"{self.code} ({self.percent_off}% off)"


class Order(models.Model):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        PAID = "paid", "Paid"
        PACKED = "packed", "Packed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Payment(models.TextChoices):
        COLLECTION = "collection", "Pay on collection"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"

    class Fulfilment(models.TextChoices):
        COLLECT = "collect", "Collect from the shop"
        DELIVER = "deliver", "Delivery"

    number = models.CharField(max_length=20, unique=True, null=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AWAITING_PAYMENT)
    payment_method = models.CharField(max_length=20, choices=Payment.choices)
    fulfilment = models.CharField(max_length=10, choices=Fulfilment.choices)
    delivery_address = models.TextField(blank=True)
    phone = models.CharField(max_length=30)

    # Frozen at the moment the order is placed; later price changes never alter an order
    subtotal_cents = models.PositiveIntegerField()
    discount_code = models.CharField(max_length=30, blank=True)
    discount_cents = models.PositiveIntegerField(default=0)
    delivery_cents = models.PositiveIntegerField(default=0)
    total_cents = models.PositiveIntegerField()
    vat_cents = models.PositiveIntegerField()

    placed_at = models.DateTimeField()
    pay_by = models.DateTimeField(help_text="Unpaid orders are cancelled after this and the stock released")
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=60, blank=True)
    packed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    refund_due = models.BooleanField(default=False)

    class Meta:
        ordering = ["-placed_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_cents=F("subtotal_cents") - F("discount_cents") + F("delivery_cents")),
                name="total_adds_up"),
            models.CheckConstraint(condition=Q(discount_cents__lte=F("subtotal_cents")), name="discount_within_subtotal"),
            models.CheckConstraint(condition=Q(vat_cents__lte=F("total_cents")), name="vat_within_total"),
            models.CheckConstraint(condition=~Q(fulfilment="deliver") | ~Q(delivery_address=""),
                                   name="delivery_needs_address"),
            models.CheckConstraint(condition=Q(paid_at__isnull=False) | Q(status__in=["awaiting_payment", "cancelled"]),
                                   name="paid_before_packing"),
        ]

    def __str__(self):
        return self.number or f"order #{self.pk}"

    @property
    def total(self):
        return fmt(self.total_cents)


class OrderLine(models.Model):
    """A snapshot of what was bought, at the price charged."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    sku = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    unit_price_cents = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    vat_rate = models.PositiveSmallIntegerField()
    discount_cents = models.PositiveIntegerField(default=0)     # this line's share of the order discount
    line_total_cents = models.PositiveIntegerField()             # after its discount share
    vat_cents = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="quantity_positive"),
            models.CheckConstraint(
                condition=Q(line_total_cents=F("unit_price_cents") * F("quantity") - F("discount_cents")),
                name="line_adds_up"),
            models.UniqueConstraint(fields=["order", "product"], name="one_line_per_product"),
        ]


class OrderEvent(models.Model):
    """The order's history: every status change, who made it and why."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=20, blank=True, choices=Order.Status.choices)
    to_status = models.CharField(max_length=20, choices=Order.Status.choices)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    note = models.CharField(max_length=200, blank=True)
    at = models.DateTimeField()

    class Meta:
        ordering = ["at", "id"]
