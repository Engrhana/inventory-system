import csv
from datetime import datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncWeek
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .access import can_export, can_manage_inventory, get_dashboard_url, is_admin_user, is_staff_user, is_standard_user
from .forms import CategoryForm, LoginForm, ProductForm, RegisterForm, SaleItemFormSet, StockInForm
from .models import AccountRequest, Category, Product, Sale, SaleItem, StockIn


def get_site_parts():
    parsed = urlsplit(settings.SITE_URL)
    protocol = parsed.scheme or 'http'
    domain = parsed.netloc or parsed.path
    return protocol, domain


def build_site_url(path=''):
    base_url = settings.SITE_URL.rstrip('/')
    if not path:
        return base_url
    return f"{base_url}/{path.lstrip('/')}"


class InventoryPasswordResetView(auth_views.PasswordResetView):
    def form_valid(self, form):
        protocol, domain = get_site_parts()
        form.save(
            use_https=protocol == 'https',
            from_email=self.from_email,
            email_template_name=self.email_template_name,
            subject_template_name=self.subject_template_name,
            request=self.request,
            html_email_template_name=self.html_email_template_name,
            extra_email_context=self.extra_email_context,
            domain_override=domain,
        )
        return super(auth_views.PasswordResetView, self).form_valid(form)


def redirect_authenticated_user(request):
    if request.session.pop('role_denied', False):
        messages.error(request, "You do not have permission to access that page.")
        return None
    if request.user.is_authenticated:
        return redirect(get_dashboard_url(request.user))
    return None


def role_required(role_check, redirect_url=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(settings.LOGIN_URL)
            if not role_check(request.user):
                request.session['role_denied'] = True
                if redirect_url:
                    return redirect(redirect_url)
                return redirect(settings.LOGIN_URL)
            return view_func(request, *args, **kwargs)

        return wrapped_view

    return decorator


admin_required = role_required(is_admin_user)
staff_dashboard_required = role_required(can_manage_inventory)
user_dashboard_required = role_required(is_standard_user)


def manage_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)
        if not can_manage_inventory(request.user):
            messages.warning(request, "You only have read-only access.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)

    return wrapped_view


def export_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)
        if not can_export(request.user):
            messages.warning(request, "You do not have permission to export reports.")
            return redirect('reports')
        return view_func(request, *args, **kwargs)

    return wrapped_view


def build_sales_series(queryset):
    def build(truncator, label_format):
        sales_data = (
            queryset.annotate(period=truncator('sale__date'))
            .values('period')
            .annotate(total=Sum('subtotal'))
            .order_by('period')
        )
        labels = [item['period'].strftime(label_format) for item in sales_data if item['period']]
        totals = [float(item['total']) for item in sales_data]
        return {'labels': labels, 'totals': totals}

    return {
        'daily': build(TruncDay, "%b %d"),
        'weekly': build(TruncWeek, "Week of %b %d"),
        'monthly': build(TruncMonth, "%b %Y"),
    }


def build_category_breakdown():
    category_breakdown = list(
        Product.objects.values('category__name')
        .annotate(product_count=Count('id'))
        .order_by('-product_count', 'category__name')
    )
    category_labels = [item['category__name'] or 'Uncategorized' for item in category_breakdown]
    category_counts = [item['product_count'] for item in category_breakdown]
    return category_labels, category_counts


def build_global_metrics():
    product_stats = Product.objects.aggregate(
        total_products=Count('id'),
        total_stock_units=Sum('stock_quantity'),
    )
    total_products = product_stats['total_products'] or 0
    total_stock_units = product_stats['total_stock_units'] or 0
    total_sales = SaleItem.objects.count()
    total_revenue = SaleItem.objects.aggregate(Sum('subtotal'))['subtotal__sum'] or 0
    total_categories = Category.objects.count()
    low_stock_products = Product.objects.select_related('category').filter(
        stock_quantity__lte=F('reorder_threshold')
    ).order_by('stock_quantity', 'name')
    low_stock_count = low_stock_products.count()

    return {
        'total_products': total_products,
        'total_categories': total_categories,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'low_stock_products': low_stock_products,
        'low_stock_count': low_stock_count,
        'total_stock_units': total_stock_units,
    }


def parse_date_bound(value, end_of_day=False):
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None

    bound_time = time.max if end_of_day else time.min
    return timezone.make_aware(datetime.combine(parsed, bound_time), timezone.get_current_timezone())


def get_filtered_saleitems(start_date='', end_date=''):
    saleitems = SaleItem.objects.select_related('sale', 'product__category').all()
    start_bound = parse_date_bound(start_date)
    end_bound = parse_date_bound(end_date, end_of_day=True)
    if start_bound:
        saleitems = saleitems.filter(sale__date__gte=start_bound)
    if end_bound:
        saleitems = saleitems.filter(sale__date__lte=end_bound)
    return saleitems


def build_report_context(start_date='', end_date=''):
    metrics = build_global_metrics()
    filtered_saleitems = get_filtered_saleitems(start_date, end_date)
    category_labels, category_counts = build_category_breakdown()
    sales_series = build_sales_series(filtered_saleitems)
    top_products = list(
        filtered_saleitems
        .values('product__name', 'product__category__name')
        .annotate(total_revenue=Sum('subtotal'), total_qty=Sum('quantity'))
        .order_by('-total_revenue')[:5]
    )

    monthly_totals = list(
        filtered_saleitems.annotate(period=TruncMonth('sale__date'))
        .values('period')
        .annotate(total=Sum('subtotal'))
        .order_by('-period')[:3]
    )
    monthly_snapshots = [
        {
            'label': item['period'].strftime('%b %Y') if item['period'] else 'Unknown',
            'total': item['total'] or Decimal('0.00'),
        }
        for item in monthly_totals
    ]

    metrics['total_sales'] = filtered_saleitems.count()
    metrics['total_revenue'] = filtered_saleitems.aggregate(total=Sum('subtotal'))['total'] or 0

    return {
        **metrics,
        'sales_series': sales_series,
        'category_labels': category_labels,
        'category_counts': category_counts,
        'monthly_snapshots': monthly_snapshots,
        'top_products': top_products,
        'start_date': start_date,
        'end_date': end_date,
        'filtered_saleitems': filtered_saleitems.order_by('-sale__date', '-id'),
    }


def build_dashboard_context():
    metrics = build_global_metrics()
    recent_sales = SaleItem.objects.select_related('product__category', 'sale').order_by('-sale__date', '-id')[:6]
    sales_series = build_sales_series(SaleItem.objects.all())
    category_labels, category_counts = build_category_breakdown()

    return {
        **metrics,
        'recent_sales': recent_sales,
        'sales_series': sales_series,
        'category_labels': category_labels,
        'category_counts': category_counts,
    }


def root_redirect(request):
    if request.user.is_authenticated:
        return redirect(get_dashboard_url(request.user))
    return redirect('login')


def login_view(request):
    redirect_response = redirect_authenticated_user(request)
    if redirect_response:
        return redirect_response

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data['username'].strip()
        password = form.cleaned_data['password']
        user = authenticate(request, username=username, password=password)

        if user and user.is_active:
            login(request, user)
            return redirect(get_dashboard_url(user))

        pending_request = AccountRequest.objects.filter(username__iexact=username).first()
        if pending_request and check_password(password, pending_request.password_hash):
            if pending_request.status == 'pending':
                messages.error(request, "Your account is pending approval.")
            elif pending_request.status == 'rejected':
                messages.error(request, "Your account request was rejected.")
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'inventory/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


def register_view(request):
    redirect_response = redirect_authenticated_user(request)
    if redirect_response:
        return redirect_response

    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        account_request = AccountRequest.objects.create(
            username=form.cleaned_data['username'],
            email=form.cleaned_data['email'],
            password_hash=make_password(form.cleaned_data['password']),
            status='pending',
        )
        admin_emails = list(
            User.objects.filter(is_superuser=True, is_active=True)
            .exclude(email='')
            .values_list('email', flat=True)
        )
        if admin_emails:
            send_mail(
                subject='New Account Request',
                message=(
                    f"{account_request.username} ({account_request.email}) has requested an account.\n"
                    "Please log in to review."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=admin_emails,
                fail_silently=True,
            )
        messages.success(
            request,
            "Your account request has been submitted. You will be notified via email once reviewed.",
        )
        return redirect('register')

    return render(request, 'inventory/register.html', {'form': form})


@user_dashboard_required
def user_dashboard(request):
    return render(request, 'inventory/dashboard.html', build_dashboard_context())


@staff_dashboard_required
def staff_dashboard(request):
    context = build_dashboard_context()
    context['staff_dashboard'] = True
    context['show_admin_tools_link'] = is_admin_user(request.user)
    return render(request, 'inventory/staff_dashboard.html', context)


@admin_required
def admin_dashboard(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action in {'approve_request', 'reject_request'}:
            account_request = get_object_or_404(AccountRequest, pk=request.POST.get('request_id'))

            if action == 'approve_request' and account_request.status == 'pending':
                if User.objects.filter(username__iexact=account_request.username).exists():
                    messages.error(request, "That username already exists in the user list.")
                elif User.objects.filter(email__iexact=account_request.email).exists():
                    messages.error(request, "That email already exists in the user list.")
                else:
                    approved_user = User(
                        username=account_request.username,
                        email=account_request.email,
                        password=account_request.password_hash,
                        is_staff=False,
                        is_active=True,
                    )
                    approved_user.save()
                    account_request.status = 'approved'
                    account_request.reviewed_at = timezone.now()
                    account_request.reviewed_by = request.user
                    account_request.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
                    send_mail(
                        subject='Account Approved',
                        message=(
                            f"Hi {account_request.username}, your account has been approved.\n"
                            f"You can now log in at {build_site_url('/login/')}"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[account_request.email],
                        fail_silently=True,
                    )
                    messages.success(request, f'{account_request.username} was approved successfully.')

            if action == 'reject_request' and account_request.status == 'pending':
                account_request.status = 'rejected'
                account_request.reviewed_at = timezone.now()
                account_request.reviewed_by = request.user
                account_request.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
                send_mail(
                    subject='Account Request Rejected',
                    message=(
                        f"Hi {account_request.username}, unfortunately your account request has been rejected."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[account_request.email],
                    fail_silently=True,
                )
                messages.success(request, f'{account_request.username} was rejected.')

        elif action in {'promote_staff', 'demote_user', 'deactivate_user'}:
            managed_user = get_object_or_404(User, pk=request.POST.get('user_id'))

            if managed_user.is_superuser:
                messages.warning(request, 'Admin accounts are managed from the terminal.')
            elif action == 'promote_staff':
                managed_user.is_staff = True
                managed_user.save(update_fields=['is_staff'])
                messages.success(request, f'{managed_user.username} is now Staff.')
            elif action == 'demote_user':
                managed_user.is_staff = False
                managed_user.save(update_fields=['is_staff'])
                messages.success(request, f'{managed_user.username} is now a User.')
            elif action == 'deactivate_user':
                managed_user.is_active = False
                managed_user.save(update_fields=['is_active'])
                messages.success(request, f'{managed_user.username} has been deactivated.')

        return redirect('admin_dashboard')

    context = {
        'pending_requests': AccountRequest.objects.filter(status='pending').order_by('created_at'),
        'rejected_requests': AccountRequest.objects.filter(status='rejected').order_by('-reviewed_at', '-created_at'),
        'all_users': User.objects.order_by('username'),
    }
    return render(request, 'inventory/admin_dashboard.html', context)


@login_required
def inventory_list(request):
    search_query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category', '').strip()

    products = Product.objects.select_related('category').order_by('name')
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query)
            | Q(barcode__icontains=search_query)
            | Q(category__name__icontains=search_query)
        )
    if category_id:
        products = products.filter(category_id=category_id)

    paginator = Paginator(products, 8)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'categories': Category.objects.order_by('name'),
        'search_query': search_query,
        'selected_category': category_id,
    }
    return render(request, 'inventory/inventory_list.html', context)


@manage_required
def category_list(request):
    categories = Category.objects.annotate(product_count=Count('product')).order_by('name')
    return render(request, 'inventory/category_list.html', {'categories': categories})


@manage_required
def category_create(request):
    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('category_list')

    context = {
        'form': form,
        'form_title': 'Add Category',
        'form_intro': 'Create a category so products can be organized and filtered clearly.',
        'submit_label': 'Save Category',
    }
    return render(request, 'inventory/category_form.html', context)


@manage_required
def category_update(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('category_list')

    context = {
        'form': form,
        'category': category,
        'form_title': f'Edit {category.name}',
        'form_intro': 'Rename this category and keep product organization consistent across the app.',
        'submit_label': 'Update Category',
    }
    return render(request, 'inventory/category_form.html', context)


@manage_required
def category_delete(request, pk):
    category = get_object_or_404(Category.objects.annotate(product_count=Count('product')), pk=pk)
    can_delete = category.product_count == 0

    if request.method == 'POST':
        if not can_delete:
            context = {
                'object_name': category.name,
                'cancel_url': 'category_list',
                'warning_text': 'Deleting a category would affect the products currently assigned to it.',
                'error_text': (
                    f'This category cannot be deleted because {category.product_count} product(s) still use it. '
                    'Move or delete those products first.'
                ),
                'can_delete': False,
            }
            return render(request, 'inventory/confirm_delete.html', context)

        category.delete()
        return redirect('category_list')

    context = {
        'object_name': category.name,
        'cancel_url': 'category_list',
        'warning_text': 'Deleting a category removes it from the available catalog structure.',
        'error_text': (
            f'This category is currently assigned to {category.product_count} product(s) and cannot be deleted.'
            if not can_delete else ''
        ),
        'can_delete': can_delete,
    }
    return render(request, 'inventory/confirm_delete.html', context)


@manage_required
def product_create(request):
    form = ProductForm(request.POST or None, include_initial_stock=True)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            product = form.save()
            initial_stock = form.cleaned_data.get('initial_stock') or 0
            if initial_stock:
                StockIn.objects.create(
                    product=product,
                    quantity=initial_stock,
                    received_by=request.user,
                    notes='Initial stock',
                )
        return redirect('inventory_list')

    context = {
        'form': form,
        'form_title': 'Add Product',
        'form_intro': 'Create a new product directly inside the app.',
        'submit_label': 'Save Product',
        'show_initial_stock': True,
    }
    return render(request, 'inventory/product_form.html', context)


@manage_required
def product_restock(request, pk):
    product = get_object_or_404(Product.objects.select_related('category'), pk=pk)
    form = StockInForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        stock_in = form.save(commit=False)
        stock_in.product = product
        stock_in.received_by = request.user
        stock_in.save()
        messages.success(request, f'{product.name} stock was increased by {stock_in.quantity}.')
        return redirect('inventory_list')

    context = {
        'form': form,
        'product': product,
        'form_title': f'Restock {product.name}',
        'form_intro': 'Record received stock so inventory changes keep an audit trail.',
        'submit_label': 'Record Stock-In',
    }
    return render(request, 'inventory/stock_in_form.html', context)


@manage_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('inventory_list')

    context = {
        'form': form,
        'product': product,
        'form_title': f'Edit {product.name}',
        'form_intro': 'Update pricing, category, or stock levels without leaving the app.',
        'submit_label': 'Update Product',
    }
    return render(request, 'inventory/product_form.html', context)


@login_required
def product_stock_history(request, pk):
    product = get_object_or_404(Product.objects.select_related('category'), pk=pk)
    stock_ins = StockIn.objects.filter(product=product).select_related('received_by').order_by('-received_at')
    return render(request, 'inventory/stock_history.html', {
        'product': product,
        'stock_ins': stock_ins,
    })


@manage_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    saleitem_count = SaleItem.objects.filter(product=product).count()
    stock_in_count = StockIn.objects.filter(product=product).count()
    can_delete = saleitem_count == 0 and stock_in_count == 0

    if request.method == 'POST':
        if not can_delete:
            context = {
                'object_name': product.name,
                'cancel_url': 'inventory_list',
                'warning_text': 'Deleting a product removes it from inventory views and future selection lists.',
                'error_text': (
                    f'This product cannot be deleted because it is linked to {saleitem_count} '
                    f'recorded sale item(s) and {stock_in_count} stock-in record(s). '
                    'Set its stock to 0 instead so inventory history stays accurate.'
                ),
                'can_delete': False,
            }
            return render(request, 'inventory/confirm_delete.html', context)

        try:
            product.delete()
        except ProtectedError:
            context = {
                'object_name': product.name,
                'cancel_url': 'inventory_list',
                'warning_text': 'Deleting a product removes it from inventory views and future selection lists.',
                'error_text': (
                    'This product could not be deleted because it is linked to inventory history. '
                    'Set its stock to 0 instead so historical reports remain correct.'
                ),
                'can_delete': False,
            }
            return render(request, 'inventory/confirm_delete.html', context)
        return redirect('inventory_list')

    context = {
        'object_name': product.name,
        'cancel_url': 'inventory_list',
        'warning_text': 'Deleting a product removes it from inventory views and future selection lists.',
        'error_text': (
            f'This product is referenced by {saleitem_count} recorded sale item(s) and '
            f'{stock_in_count} stock-in record(s) and cannot be deleted.'
            if not can_delete else ''
        ),
        'can_delete': can_delete,
    }
    return render(request, 'inventory/confirm_delete.html', context)


@login_required
def sales_list(request):
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    staff_query = request.GET.get('staff', '').strip()

    sales = Sale.objects.select_related('user').prefetch_related(
        Prefetch('items', queryset=SaleItem.objects.select_related('product__category').order_by('id'))
    ).annotate(
        total_amount=Sum('items__subtotal'),
        item_count=Count('items'),
    ).order_by('-date')

    start_bound = parse_date_bound(start_date)
    end_bound = parse_date_bound(end_date, end_of_day=True)
    if start_bound:
        sales = sales.filter(date__gte=start_bound)
    if end_bound:
        sales = sales.filter(date__lte=end_bound)
    if staff_query:
        sales = sales.filter(user__username__icontains=staff_query)

    staff_users = User.objects.filter(
        Q(is_staff=True) | Q(is_superuser=True)
    ).order_by('username')
    sales_total_revenue = sales.aggregate(total=Sum('items__subtotal'))['total'] or 0

    sales_total_count = sales.count()

    context = {
        'sales': sales,
        'start_date': start_date,
        'end_date': end_date,
        'staff_query': staff_query,
        'staff_users': staff_users,
        'sales_total_revenue': sales_total_revenue,
        'sales_total_count': sales_total_count,
    }
    return render(request, 'inventory/sales_list.html', context)


@login_required
def sale_receipt(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related('user').prefetch_related(
            Prefetch('items', queryset=SaleItem.objects.select_related('product__category').order_by('id'))
        ),
        pk=pk,
    )
    total_amount = sale.items.aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')

    context = {
        'sale': sale,
        'total_amount': total_amount,
    }
    return render(request, 'inventory/sale_receipt.html', context)


def parse_sale_decimal(value, default='0'):
    try:
        amount = Decimal(str(value or default).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        amount = Decimal(default)
    return max(amount, Decimal('0'))


def quantize_money(amount):
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def apply_sale_payment_details(sale, post_data, formset):
    subtotal = Decimal('0.00')
    for form in formset.forms:
        if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
            continue
        if form.cleaned_data.get('DELETE', False):
            continue

        product = form.cleaned_data.get('product')
        quantity = form.cleaned_data.get('quantity') or 0
        if product and quantity:
            subtotal += product.price * quantity

    tax_rate = min(parse_sale_decimal(post_data.get('tax_rate')), Decimal('100'))
    discount_rate = min(parse_sale_decimal(post_data.get('discount_rate')), Decimal('100'))
    amount_paid = parse_sale_decimal(post_data.get('amount_paid'))
    tax_amount = quantize_money(subtotal * tax_rate / Decimal('100'))
    discount_amount = quantize_money(subtotal * discount_rate / Decimal('100'))
    grand_total = quantize_money(max(subtotal + tax_amount - discount_amount, Decimal('0')))
    change_amount = quantize_money(max(amount_paid - grand_total, Decimal('0')))

    sale.tax_rate = tax_rate
    sale.discount_rate = discount_rate
    sale.tax_amount = tax_amount
    sale.discount_amount = discount_amount
    sale.amount_paid = quantize_money(amount_paid)
    sale.grand_total = grand_total
    sale.change_amount = change_amount


def get_top_sale_products():
    return (
        Product.objects.select_related('category')
        .annotate(total_sold=Coalesce(Sum('saleitem__quantity'), 0))
        .order_by('-total_sold', 'name')[:10]
    )


@manage_required
def sale_create(request):
    sale = Sale(user=request.user)
    formset = SaleItemFormSet(request.POST or None, instance=sale, prefix='items')
    if request.method == 'POST' and formset.is_valid():
        apply_sale_payment_details(sale, request.POST, formset)
        sale.save()
        formset.instance = sale
        formset.save()
        return redirect('sales_list')

    context = {
        'formset': formset,
        'form_title': 'Create Sale',
        'form_intro': 'Add one or more sale items and the stock counts will update automatically.',
        'submit_label': 'Save Sale',
        'top_sale_products': get_top_sale_products(),
    }
    return render(request, 'inventory/sale_form.html', context)


@manage_required
def sale_update(request, pk):
    sale = get_object_or_404(Sale.objects.prefetch_related('items'), pk=pk)
    formset = SaleItemFormSet(request.POST or None, instance=sale, prefix='items')
    if request.method == 'POST' and formset.is_valid():
        apply_sale_payment_details(sale, request.POST, formset)
        sale.save()
        formset.save()
        return redirect('sales_list')

    context = {
        'sale': sale,
        'formset': formset,
        'form_title': f'Edit Sale #{sale.id}',
        'form_intro': 'Adjust items in this sale and stock will be recalculated safely.',
        'submit_label': 'Update Sale',
        'top_sale_products': get_top_sale_products(),
    }
    return render(request, 'inventory/sale_form.html', context)


@manage_required
def sale_delete(request, pk):
    sale = get_object_or_404(Sale.objects.prefetch_related('items__product'), pk=pk)
    if request.method == 'POST':
        sale.delete()
        return redirect('sales_list')

    context = {
        'object_name': f'Sale #{sale.id}',
        'cancel_url': 'sales_list',
        'warning_text': 'Deleting this sale will restore its item quantities back into stock.',
        'can_delete': True,
    }
    return render(request, 'inventory/confirm_delete.html', context)


@login_required
def reports(request):
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    return render(request, 'inventory/reports.html', build_report_context(start_date, end_date))


@export_required
def export_reports_excel(request):
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    context = build_report_context(start_date, end_date)

    response = HttpResponse(content_type='text/tab-separated-values; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="inventory-report.tsv"'

    writer = csv.writer(response, delimiter='\t')
    writer.writerow(['Inventory Report'])
    writer.writerow(['Start Date', start_date or 'All'])
    writer.writerow(['End Date', end_date or 'All'])
    writer.writerow([])
    writer.writerow(['Summary'])
    writer.writerow(['Total Products', context['total_products']])
    writer.writerow(['Sale Items', context['total_sales']])
    writer.writerow(['Revenue', f"{context['total_revenue']:.2f}"])
    writer.writerow(['Low Stock Products', context['low_stock_count']])
    writer.writerow([])
    writer.writerow(['Detailed Sales'])
    writer.writerow(['Sale ID', 'Date', 'Product', 'Category', 'Quantity', 'Subtotal'])

    for item in context['filtered_saleitems']:
        writer.writerow([
            item.sale_id,
            f"{timezone.localtime(item.sale.date).strftime('%Y-%m-%d %H:%M')} PHT",
            item.product.name,
            item.product.category.name,
            item.quantity,
            f"{item.subtotal:.2f}",
        ])

    writer.writerow([])
    writer.writerow(['Top 5 Products by Revenue'])
    writer.writerow(['Product', 'Category', 'Units Sold', 'Revenue'])
    for item in context['top_products']:
        writer.writerow([
            item['product__name'],
            item['product__category__name'],
            item['total_qty'],
            f"{item['total_revenue']:.2f}",
        ])

    return response


@export_required
def export_reports_pdf(request):
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    context = build_report_context(start_date, end_date)
    return render(request, 'inventory/reports_print.html', context)
