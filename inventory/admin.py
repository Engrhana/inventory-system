from django.contrib import admin
from django.db.models import Count, Sum

from .models import AccountRequest, Category, Product, Sale, SaleItem, StockIn


admin.site.site_header = "Ethan's Variety Store Admin"
admin.site.site_title = "Ethan's Variety Store Admin"
admin.site.index_title = "Manage catalog, stock, and sales"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(AccountRequest)
class AccountRequestAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'status', 'created_at', 'reviewed_at', 'reviewed_by')
    list_filter = ('status', 'created_at', 'reviewed_at')
    search_fields = ('username', 'email')
    ordering = ('-created_at',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'barcode', 'category', 'price', 'stock_quantity', 'reorder_threshold', 'stock_status')
    list_filter = ('category',)
    search_fields = ('name', 'barcode', 'category__name')
    ordering = ('name',)
    readonly_fields = ('stock_quantity',)

    @admin.display(description='Status')
    def stock_status(self, obj):
        return 'Low stock' if obj.is_low_stock else 'Healthy'


@admin.register(StockIn)
class StockInAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'received_at', 'received_by')
    list_filter = ('received_at', 'product__category')
    search_fields = ('product__name', 'product__barcode', 'product__category__name', 'received_by__username')
    autocomplete_fields = ('product', 'received_by')
    readonly_fields = ('received_at',)

    def has_delete_permission(self, request, obj=None):
        return False


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    autocomplete_fields = ('product',)
    fields = ('product', 'quantity', 'subtotal')
    readonly_fields = ('subtotal',)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'date', 'item_count', 'total_amount')
    list_filter = ('date', 'user')
    search_fields = ('id', 'user__username', 'items__product__name', 'items__product__barcode')
    readonly_fields = ('date',)
    date_hierarchy = 'date'
    inlines = [SaleItemInline]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(_item_count=Count('items'), _total_amount=Sum('items__subtotal'))

    @admin.display(description='Items')
    def item_count(self, obj):
        return obj._item_count

    @admin.display(description='Total')
    def total_amount(self, obj):
        return obj._total_amount or 0


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'subtotal')
    list_filter = ('sale__date', 'product__category')
    search_fields = ('sale__id', 'product__name', 'product__barcode', 'product__category__name')
    autocomplete_fields = ('sale', 'product')
