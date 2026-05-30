import json
from itertools import groupby

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import AccountRequest, Category, Product, Sale, SaleItem, StockIn


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
    )


class RegisterForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose a username'}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
    )
    password = forms.CharField(
        required=True,
        min_length=8,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
        help_text='Use at least 8 characters.',
    )
    confirm_password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("That username is already taken.")
        if AccountRequest.objects.filter(username__iexact=username).exists():
            raise ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        if AccountRequest.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category name'}),
        }


class ProductForm(forms.ModelForm):
    initial_stock = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.order_by('name'),
        empty_label="Select a category",
    )

    def __init__(self, *args, include_initial_stock=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not include_initial_stock:
            self.fields.pop('initial_stock')

    def clean_barcode(self):
        barcode = self.cleaned_data.get('barcode')
        if not barcode:
            return None
        return barcode.strip() or None

    class Meta:
        model = Product
        fields = ['name', 'barcode', 'category', 'price', 'reorder_threshold']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product name'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Barcode number or scan code'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'reorder_threshold': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }


class StockInForm(forms.ModelForm):
    class Meta:
        model = StockIn
        fields = ['quantity', 'notes']
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional - e.g. Supplier delivery, Stock count correction',
            }),
        }


class SaleItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        products = list(Product.objects.select_related('category').order_by('category__name', 'name'))
        grouped_choices = [('', 'Select a product')]
        self.fields['quantity'].min_value = 1

        for category, category_products in groupby(products, key=lambda product: product.category.name):
            options = []
            for product in category_products:
                option = (product.pk, product.name)
                options.append(option)
            grouped_choices.append((category, options))

        self.fields['product'].queryset = Product.objects.filter(pk__in=[product.pk for product in products])
        self.fields['product'].choices = grouped_choices
        self.fields['product'].widget.attrs['data-prices'] = json.dumps(
            {str(product.pk): str(product.price) for product in products}
        )
        self.fields['product'].widget.attrs['data-stocks'] = json.dumps(
            {str(product.pk): product.stock_quantity for product in products}
        )
        self.fields['product'].widget.attrs['data-barcodes'] = json.dumps(
            {str(product.pk): product.barcode or '' for product in products}
        )

    class Meta:
        model = SaleItem
        fields = ['product', 'quantity']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select', 'data-product-select': 'true'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        }


class RequiredSaleItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen_products = []
        has_item = False
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                product = form.cleaned_data.get('product')
                quantity = form.cleaned_data.get('quantity')
                if product and quantity:
                    has_item = True
                    if product in seen_products:
                        raise ValidationError(
                            f'"{product.name}" appears more than once. '
                            'Combine the quantities into a single row instead.'
                        )
                    seen_products.append(product)
        if not has_item:
            raise ValidationError("Add at least one sale item before saving the sale.")


SaleItemFormSet = inlineformset_factory(
    Sale,
    SaleItem,
    form=SaleItemForm,
    formset=RequiredSaleItemFormSet,
    extra=1,
    can_delete=True,
)
