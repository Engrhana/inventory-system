from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


def default_reorder_threshold():
    return getattr(settings, 'LOW_STOCK_THRESHOLD', 5)


def _apply_stock_delta(product_id, delta):
    """Add delta (positive or negative) to a product's stock inside an existing transaction."""
    product = Product.objects.select_for_update().get(pk=product_id)
    product.stock_quantity += delta
    product.save(update_fields=['stock_quantity'])
    return product


class AccountRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_requests',
    )

    def __str__(self):
        return f"{self.username} ({self.email})"

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    barcode = models.CharField(max_length=64, unique=True, blank=True, null=True)
    stock_quantity = models.PositiveIntegerField(default=0, editable=False)
    reorder_threshold = models.PositiveIntegerField(default=default_reorder_threshold)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        if self.barcode:
            self.barcode = self.barcode.strip() or None
        else:
            self.barcode = None
        super().save(*args, **kwargs)

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.reorder_threshold

    def __str__(self):
        return self.name


class StockIn(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='stock_ins')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    received_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='stock_ins',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('-received_at', '-id')

    def clean(self):
        super().clean()
        if self.quantity < 1:
            raise ValidationError({'quantity': "Quantity must be at least 1."})
        if not self.pk:
            return

        previous = StockIn.objects.get(pk=self.pk)
        if previous.product_id != self.product_id or previous.quantity != self.quantity:
            raise ValidationError("Stock-in product and quantity cannot be changed after saving.")

    def save(self, *args, **kwargs):
        if self.quantity < 1:
            raise ValidationError({'quantity': "Quantity must be at least 1."})
        with transaction.atomic():
            is_new = self.pk is None
            if is_new:
                product = Product.objects.select_for_update().get(pk=self.product_id)
            else:
                previous = StockIn.objects.select_for_update().get(pk=self.pk)
                if previous.product_id != self.product_id or previous.quantity != self.quantity:
                    raise ValidationError("Stock-in product and quantity cannot be changed after saving.")
                product = None

            super().save(*args, **kwargs)

            if is_new:
                product.stock_quantity += self.quantity
                product.save(update_fields=['stock_quantity'])

    def __str__(self):
        return f"{self.product.name} +{self.quantity}"


class Sale(models.Model):
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sales',
    )  # Admin or Staff
    date = models.DateTimeField(auto_now_add=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    change_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Sale {self.id} - {self.date}"

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            for item in self.items.select_related('product'):
                _apply_stock_delta(item.product_id, item.quantity)
            return super().delete(*args, **kwargs)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, blank=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.pk:
                previous_item = SaleItem.objects.select_related('product').get(pk=self.pk)
                _apply_stock_delta(previous_item.product_id, previous_item.quantity)

            current_product = Product.objects.select_for_update().get(pk=self.product_id)

            if self.quantity > current_product.stock_quantity:
                raise ValidationError("Not enough stock available.")

            self.subtotal = current_product.price * self.quantity
            current_product.stock_quantity -= self.quantity
            current_product.save(update_fields=['stock_quantity'])

            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            _apply_stock_delta(self.product_id, self.quantity)
            return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
