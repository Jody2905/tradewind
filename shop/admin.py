from django.contrib import admin

from .models import Category, DiscountCode, Order, OrderEvent, OrderLine, Product, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["sku", "name", "category", "price", "vat_rate", "stock", "active"]
    list_filter = ["category", "active", "vat_rate"]
    search_fields = ["sku", "name"]
    prepopulated_fields = {"slug": ["name"]}
    readonly_fields = ["stock"]          # stock only changes through restock / count correction, so it's always recorded


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ["at", "product", "change", "balance_after", "reason", "order", "by"]
    list_filter = ["reason"]

    def has_add_permission(self, request):          # the ledger is written by the shop, never by hand
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "percent_off", "valid_from", "valid_until", "times_used", "max_uses", "active"]
    readonly_fields = ["times_used"]


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in OrderLine._meta.fields]


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in OrderEvent._meta.fields]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "status", "total", "payment_method", "fulfilment", "placed_at"]
    list_filter = ["status", "payment_method", "fulfilment"]
    search_fields = ["number", "customer__email", "customer__first_name", "customer__last_name"]
    inlines = [OrderLineInline, OrderEventInline]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Order._meta.fields]   # orders change only through the shop's actions

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = "Tradewind admin"
admin.site.site_title = "Tradewind admin"
admin.site.index_title = "Shop management"
