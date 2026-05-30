from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from .models import AccountRequest, Category, Product, Sale, SaleItem, StockIn


class SaleItemModelTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='stockmanager',
            password='password123',
            is_superuser=True,
            is_staff=True,
            email='stockmanager@example.com',
        )
        self.category = Category.objects.create(name='Pantry')
        self.product = Product.objects.create(
            category=self.category,
            name='Rice',
            stock_quantity=10,
            price=50,
        )
        self.sale = Sale.objects.create(user=self.admin_user)

    def test_creating_sale_item_reduces_stock_and_sets_subtotal(self):
        item = SaleItem.objects.create(sale=self.sale, product=self.product, quantity=4)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)
        self.assertEqual(float(item.subtotal), 200.0)

    def test_selling_more_than_available_stock_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            SaleItem.objects.create(sale=self.sale, product=self.product, quantity=11)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='admin@example.com',
    SITE_URL='http://inventory.test:8000',
)
class InventoryViewsTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='manager',
            password='password123',
            is_superuser=True,
            is_staff=True,
            email='manager@example.com',
        )
        self.staff_user = User.objects.create_user(
            username='staffer',
            password='password123',
            is_staff=True,
            email='staffer@example.com',
        )
        self.viewer_user = User.objects.create_user(
            username='viewer',
            password='password123',
            is_staff=False,
            is_superuser=False,
            email='viewer@example.com',
        )

        self.beverages = Category.objects.create(name='Beverages')
        self.snacks = Category.objects.create(name='Snacks')

        self.cola = Product.objects.create(
            category=self.beverages,
            name='Cola',
            barcode='4800001112223',
            stock_quantity=20,
            price=25,
        )
        self.chips = Product.objects.create(
            category=self.snacks,
            name='Chips',
            barcode='4800003334445',
            stock_quantity=4,
            price=15,
        )
        self.water = Product.objects.create(category=self.beverages, name='Water', stock_quantity=12, price=10)

        older_sale = Sale.objects.create(user=self.staff_user)
        newer_sale = Sale.objects.create(user=self.staff_user)

        Sale.objects.filter(id=older_sale.id).update(date=timezone.now() - timedelta(days=14))
        Sale.objects.filter(id=newer_sale.id).update(date=timezone.now() - timedelta(days=2))
        self.older_sale = Sale.objects.get(id=older_sale.id)
        self.newer_sale = Sale.objects.get(id=newer_sale.id)

        SaleItem.objects.create(sale=self.older_sale, product=self.cola, quantity=2)
        self.chips.refresh_from_db()
        SaleItem.objects.create(sale=self.newer_sale, product=self.chips, quantity=1)
        self.water.refresh_from_db()
        SaleItem.objects.create(sale=self.newer_sale, product=self.water, quantity=1)

    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/login.html')

    def test_register_page_renders(self):
        response = self.client.get(reverse('register'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/register.html')

    def test_register_creates_pending_request(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'InventoryPass123',
            'confirm_password': 'InventoryPass123',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(AccountRequest.objects.filter(username='newuser', status='pending').exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('newuser (newuser@example.com) has requested an account.', mail.outbox[0].body)

    def test_register_duplicate_username_blocked(self):
        AccountRequest.objects.create(
            username='duplicateuser',
            email='pending@example.com',
            password_hash=make_password('InventoryPass123'),
        )

        response = self.client.post(reverse('register'), {
            'username': 'duplicateuser',
            'email': 'other@example.com',
            'password': 'InventoryPass123',
            'confirm_password': 'InventoryPass123',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'That username is already taken.')

    def test_register_duplicate_email_blocked(self):
        AccountRequest.objects.create(
            username='pendinguser',
            email='duplicate@example.com',
            password_hash=make_password('InventoryPass123'),
        )

        response = self.client.post(reverse('register'), {
            'username': 'anotheruser',
            'email': 'duplicate@example.com',
            'password': 'InventoryPass123',
            'confirm_password': 'InventoryPass123',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'An account with this email already exists.')

    def test_register_password_mismatch_blocked(self):
        response = self.client.post(reverse('register'), {
            'username': 'mismatch',
            'email': 'mismatch@example.com',
            'password': 'InventoryPass123',
            'confirm_password': 'MismatchPass123',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Passwords do not match.')

    def test_login_approved_user_redirects_to_dashboard(self):
        approved_user = User.objects.create_user(
            username='approved',
            password='InventoryPass123',
            email='approved@example.com',
        )

        response = self.client.post(reverse('login'), {
            'username': approved_user.username,
            'password': 'InventoryPass123',
        })

        self.assertRedirects(response, reverse('dashboard'))

    def test_login_pending_user_shows_error(self):
        AccountRequest.objects.create(
            username='pendinguser',
            email='pending@example.com',
            password_hash=make_password('InventoryPass123'),
            status='pending',
        )

        response = self.client.post(reverse('login'), {
            'username': 'pendinguser',
            'password': 'InventoryPass123',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your account is pending approval.')

    def test_login_rejected_user_shows_error(self):
        AccountRequest.objects.create(
            username='rejecteduser',
            email='rejected@example.com',
            password_hash=make_password('InventoryPass123'),
            status='rejected',
        )

        response = self.client.post(reverse('login'), {
            'username': 'rejecteduser',
            'password': 'InventoryPass123',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your account request was rejected.')

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse('dashboard'))

        self.assertRedirects(response, reverse('login'))

    def test_dashboard_page_renders_with_chart_context(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/dashboard.html')
        self.assertIn('daily', response.context['sales_series'])
        self.assertEqual(response.context['category_labels'], ['Beverages', 'Snacks'])
        self.assertEqual(response.context['category_counts'], [2, 1])
        self.assertEqual(response.context['low_stock_count'], 1)

    def test_low_stock_uses_product_reorder_threshold(self):
        self.water.reorder_threshold = 15
        self.water.save(update_fields=['reorder_threshold'])
        self.client.force_login(self.viewer_user)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.context['low_stock_count'], 2)
        self.assertIn(self.water, response.context['low_stock_products'])

    def test_inventory_page_renders_for_signed_in_user(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('inventory_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/inventory_list.html')
        self.assertEqual(response.context['page_obj'].paginator.count, 3)

    def test_inventory_search_filter(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('inventory_list'), {'q': 'cola'})

        products = list(response.context['page_obj'])
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, 'Cola')

    def test_inventory_search_filter_matches_barcode(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('inventory_list'), {'q': '3334445'})

        products = list(response.context['page_obj'])
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, 'Chips')

    def test_inventory_category_filter(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('inventory_list'), {'category': self.snacks.id})

        products = list(response.context['page_obj'])
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, 'Chips')

    def test_non_staff_cannot_access_product_create(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('product_create'))

        self.assertRedirects(response, reverse('dashboard'))

    def test_non_staff_cannot_access_category_management(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('category_list'))

        self.assertRedirects(response, reverse('dashboard'))

    def test_category_list_renders_for_staff(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('category_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/category_list.html')
        self.assertContains(response, 'Beverages')

    def test_category_create(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse('category_create'), {
            'name': 'Household',
        })

        self.assertRedirects(response, reverse('category_list'))
        self.assertTrue(Category.objects.filter(name='Household').exists())

    def test_category_update(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse('category_update', args=[self.snacks.id]), {
            'name': 'Snack Foods',
        })

        self.assertRedirects(response, reverse('category_list'))
        self.snacks.refresh_from_db()
        self.assertEqual(self.snacks.name, 'Snack Foods')

    def test_category_delete(self):
        self.client.force_login(self.staff_user)
        office = Category.objects.create(name='Office')
        response = self.client.post(reverse('category_delete', args=[office.id]))

        self.assertRedirects(response, reverse('category_list'))
        self.assertFalse(Category.objects.filter(id=office.id).exists())

    def test_category_delete_blocks_categories_with_products(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse('category_delete', args=[self.beverages.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cannot be deleted')
        self.assertTrue(Category.objects.filter(id=self.beverages.id).exists())

    def test_category_delete_is_protected_at_model_level(self):
        with self.assertRaises(ProtectedError):
            self.beverages.delete()

    def test_product_create(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse('product_create'), {
            'name': 'Soap',
            'barcode': '',
            'category': self.snacks.id,
            'price': '30.00',
            'reorder_threshold': 3,
            'initial_stock': 9,
        })

        self.assertRedirects(response, reverse('inventory_list'))
        product = Product.objects.get(name='Soap')
        self.assertIsNone(product.barcode)
        self.assertEqual(product.stock_quantity, 9)
        self.assertEqual(product.reorder_threshold, 3)
        self.assertTrue(StockIn.objects.filter(product=product, quantity=9, received_by=self.staff_user).exists())

    def test_product_update(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse('product_update', args=[self.cola.id]), {
            'name': 'Cola Zero',
            'barcode': ' 4800009990001 ',
            'category': self.beverages.id,
            'price': '28.00',
            'reorder_threshold': 8,
        })

        self.assertRedirects(response, reverse('inventory_list'))
        self.cola.refresh_from_db()
        self.assertEqual(self.cola.name, 'Cola Zero')
        self.assertEqual(self.cola.barcode, '4800009990001')
        self.assertEqual(float(self.cola.price), 28.0)
        self.assertEqual(self.cola.reorder_threshold, 8)

    def test_product_restock_adds_stock_in_record(self):
        self.client.force_login(self.staff_user)
        self.cola.refresh_from_db()
        starting_stock = self.cola.stock_quantity

        response = self.client.post(reverse('product_restock', args=[self.cola.id]), {
            'quantity': 6,
        })

        self.assertRedirects(response, reverse('inventory_list'))
        self.cola.refresh_from_db()
        self.assertEqual(self.cola.stock_quantity, starting_stock + 6)
        stock_in = StockIn.objects.get(product=self.cola, quantity=6)
        self.assertEqual(stock_in.received_by, self.staff_user)
        self.assertEqual(stock_in.notes, '')

    def test_product_delete(self):
        self.client.force_login(self.staff_user)
        soap = Product.objects.create(category=self.snacks, name='Soap', stock_quantity=9, price=30)
        response = self.client.post(reverse('product_delete', args=[soap.id]))

        self.assertRedirects(response, reverse('inventory_list'))
        self.assertFalse(Product.objects.filter(id=soap.id).exists())

    def test_product_delete_blocks_products_with_sale_history(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse('product_delete', args=[self.water.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cannot be deleted')
        self.assertTrue(Product.objects.filter(id=self.water.id).exists())

    def test_sales_page_renders_for_signed_in_user(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('sales_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/sales_list.html')
        self.assertEqual(response.context['sales_total_count'], 2)
        self.assertContains(response, 'Receipt')

    def test_sale_receipt_renders_for_signed_in_user(self):
        self.newer_sale.tax_rate = 12
        self.newer_sale.discount_rate = 5
        self.newer_sale.tax_amount = 3
        self.newer_sale.discount_amount = 1.25
        self.newer_sale.grand_total = 26.75
        self.newer_sale.amount_paid = 30
        self.newer_sale.change_amount = 3.25
        self.newer_sale.save()

        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('sale_receipt', args=[self.newer_sale.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/sale_receipt.html')
        self.assertContains(response, f'Receipt #{self.newer_sale.id}')
        self.assertContains(response, 'Print Receipt')
        self.assertContains(response, 'PHP 25.00')
        self.assertContains(response, 'Tax (12.00%)')
        self.assertContains(response, 'Discount (5.00%)')
        self.assertContains(response, 'PHP 30.00')
        self.assertContains(response, 'PHP 3.25')

    def test_sales_date_filter(self):
        self.client.force_login(self.viewer_user)
        start_date = (timezone.localdate() - timedelta(days=5)).isoformat()
        end_date = timezone.localdate().isoformat()

        response = self.client.get(reverse('sales_list'), {
            'start_date': start_date,
            'end_date': end_date,
        })

        sales = list(response.context['sales'])
        self.assertEqual(len(sales), 1)
        self.assertEqual(sales[0].id, self.newer_sale.id)

    def test_sales_empty_state(self):
        self.client.force_login(self.viewer_user)
        start_date = (timezone.localdate() + timedelta(days=1)).isoformat()
        end_date = (timezone.localdate() + timedelta(days=2)).isoformat()

        response = self.client.get(reverse('sales_list'), {
            'start_date': start_date,
            'end_date': end_date,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['sales_total_count'], 0)
        self.assertContains(response, 'No sales matched the selected date range.')

    def test_sales_list_shows_sales_without_pagination(self):
        """Sales list should show transactions directly without pagination controls."""
        self.client.login(username='manager', password='password123')
        response = self.client.get(reverse('sales_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('sales', response.context)
        self.assertNotContains(response, 'Previous')
        self.assertNotContains(response, 'Next')

    def test_sales_list_staff_filter(self):
        """Staff filter should limit sales to that user."""
        self.client.login(username='manager', password='password123')
        response = self.client.get(reverse('sales_list'), {'staff': 'staffer'})
        self.assertEqual(response.status_code, 200)
        for sale in response.context['sales']:
            self.assertEqual(sale.user.username, 'staffer')

    def test_stock_history_page_renders_for_any_user(self):
        """Any authenticated user can view the stock history page."""
        self.client.login(username='viewer', password='password123')
        response = self.client.get(reverse('product_stock_history', args=[self.cola.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.cola.name)

    def test_sale_with_null_user_shows_deleted_user(self):
        """A sale with user=None should display 'Deleted User' without crashing."""
        self.client.login(username='manager', password='password123')
        orphan_sale = Sale.objects.create(user=None)
        SaleItem.objects.create(sale=orphan_sale, product=self.water, quantity=1)
        response = self.client.get(reverse('sales_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Deleted User')

    def test_duplicate_product_in_sale_blocked(self):
        """Submitting the same product twice in one sale should fail validation."""
        self.client.login(username='manager', password='password123')
        response = self.client.post(reverse('sale_create'), {
            'items-TOTAL_FORMS': '2',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.cola.pk,
            'items-0-quantity': 1,
            'items-1-product': self.cola.pk,
            'items-1-quantity': 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'appears more than once')

    def test_sale_create_reduces_stock(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse('sale_create'), {
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.cola.id,
            'items-0-quantity': '3',
            'tax_rate': '10',
            'discount_rate': '5',
            'amount_paid': '100',
        })

        self.assertRedirects(response, reverse('sales_list'))
        self.cola.refresh_from_db()
        self.assertEqual(self.cola.stock_quantity, 15)
        latest_sale = Sale.objects.order_by('-id').first()
        self.assertEqual(latest_sale.items.count(), 1)
        self.assertEqual(float(latest_sale.tax_rate), 10.0)
        self.assertEqual(float(latest_sale.discount_rate), 5.0)
        self.assertEqual(float(latest_sale.tax_amount), 7.5)
        self.assertEqual(float(latest_sale.discount_amount), 3.75)
        self.assertEqual(float(latest_sale.grand_total), 78.75)
        self.assertEqual(float(latest_sale.amount_paid), 100.0)
        self.assertEqual(float(latest_sale.change_amount), 21.25)

    def test_sale_create_page_supports_adding_more_items(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('sale_create'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Add Another Item')
        self.assertContains(response, 'Search products, categories, or barcodes')
        self.assertContains(response, 'data-barcodes')
        self.assertContains(response, self.cola.barcode)
        self.assertContains(response, 'data-percent-input')
        self.assertContains(response, '<optgroup label="Beverages">')

    def test_sale_update_recalculates_stock(self):
        self.client.force_login(self.staff_user)
        item = self.older_sale.items.first()

        response = self.client.post(reverse('sale_update', args=[self.older_sale.id]), {
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '1',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-id': str(item.id),
            'items-0-product': self.cola.id,
            'items-0-quantity': '1',
        })

        self.assertRedirects(response, reverse('sales_list'))
        self.cola.refresh_from_db()
        self.assertEqual(self.cola.stock_quantity, 19)

    def test_sale_delete_restores_stock(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(reverse('sale_delete', args=[self.newer_sale.id]))

        self.assertRedirects(response, reverse('sales_list'))
        self.chips.refresh_from_db()
        self.water.refresh_from_db()
        self.assertEqual(self.chips.stock_quantity, 4)
        self.assertEqual(self.water.stock_quantity, 12)

    def test_sale_history_remains_when_staff_user_is_deleted(self):
        self.staff_user.delete()

        self.older_sale.refresh_from_db()
        self.newer_sale.refresh_from_db()
        self.assertIsNone(self.older_sale.user)
        self.assertIsNone(self.newer_sale.user)

    def test_reports_page_renders_with_expected_context_for_signed_in_user(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/reports.html')
        self.assertEqual(response.context['total_products'], 3)
        self.assertEqual(response.context['low_stock_count'], 1)
        self.assertIn('monthly', response.context['sales_series'])
        self.assertTrue(response.context['monthly_snapshots'])

    def test_reports_date_filter_updates_sales_metrics(self):
        self.client.force_login(self.viewer_user)
        start_date = (timezone.localdate() - timedelta(days=5)).isoformat()
        end_date = timezone.localdate().isoformat()

        response = self.client.get(reverse('reports'), {
            'start_date': start_date,
            'end_date': end_date,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_sales'], 2)
        self.assertEqual(float(response.context['total_revenue']), 25.0)

    def test_non_staff_cannot_export_reports(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('export_reports_excel'))

        self.assertRedirects(response, reverse('reports'))

    def test_reports_excel_export_downloads_filtered_file(self):
        self.client.force_login(self.staff_user)
        start_date = (timezone.localdate() - timedelta(days=5)).isoformat()
        end_date = timezone.localdate().isoformat()

        response = self.client.get(reverse('export_reports_excel'), {
            'start_date': start_date,
            'end_date': end_date,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/tab-separated-values; charset=utf-8')
        self.assertIn('attachment; filename="inventory-report.tsv"', response['Content-Disposition'])
        self.assertContains(response, 'Inventory Report')
        self.assertContains(response, 'Chips')
        self.assertNotContains(response, 'Cola')

    def test_reports_print_view_renders_filtered_content(self):
        self.client.force_login(self.staff_user)
        start_date = (timezone.localdate() - timedelta(days=5)).isoformat()
        end_date = timezone.localdate().isoformat()

        response = self.client.get(reverse('export_reports_pdf'), {
            'start_date': start_date,
            'end_date': end_date,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/reports_print.html')
        self.assertContains(response, 'Print / Save as PDF')
        self.assertContains(response, "browser's Print / Save as PDF option")
        self.assertContains(response, 'Chips')
        self.assertNotContains(response, 'Cola')
        self.assertContains(response, 'PHT')

    def test_admin_can_approve_request(self):
        self.client.force_login(self.admin_user)
        account_request = AccountRequest.objects.create(
            username='pendingperson',
            email='pending@example.com',
            password_hash=make_password('InventoryPass123'),
        )

        response = self.client.post(reverse('admin_dashboard'), {
            'action': 'approve_request',
            'request_id': account_request.id,
        })

        self.assertRedirects(response, reverse('admin_dashboard'))
        account_request.refresh_from_db()
        self.assertEqual(account_request.status, 'approved')
        self.assertIsNotNone(account_request.reviewed_at)
        self.assertEqual(account_request.reviewed_by, self.admin_user)
        self.assertTrue(User.objects.filter(username='pendingperson', is_staff=False).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('http://inventory.test:8000/login/', mail.outbox[0].body)

    def test_forgot_password_email_uses_configured_site_url(self):
        self.client.post(reverse('forgot_password'), {
            'email': self.viewer_user.email,
        })

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('http://inventory.test:8000/reset/', mail.outbox[0].body)

    def test_admin_can_reject_request(self):
        self.client.force_login(self.admin_user)
        account_request = AccountRequest.objects.create(
            username='rejectme',
            email='reject@example.com',
            password_hash=make_password('InventoryPass123'),
        )

        response = self.client.post(reverse('admin_dashboard'), {
            'action': 'reject_request',
            'request_id': account_request.id,
        })

        self.assertRedirects(response, reverse('admin_dashboard'))
        account_request.refresh_from_db()
        self.assertEqual(account_request.status, 'rejected')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('has been rejected', mail.outbox[0].body)

    def test_admin_can_promote_user_to_staff(self):
        self.client.force_login(self.admin_user)
        promoted_user = User.objects.create_user(username='promoteme', password='password123')

        response = self.client.post(reverse('admin_dashboard'), {
            'action': 'promote_staff',
            'user_id': promoted_user.id,
        })

        self.assertRedirects(response, reverse('admin_dashboard'))
        promoted_user.refresh_from_db()
        self.assertTrue(promoted_user.is_staff)

    def test_staff_dashboard_requires_staff_role(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('staff_dashboard'))

        self.assertRedirects(response, reverse('login'))

    def test_staff_cannot_access_admin_dashboard(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('admin_dashboard'))

        self.assertRedirects(response, reverse('login'))

    def test_user_cannot_access_staff_dashboard(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('staff_dashboard'))

        self.assertRedirects(response, reverse('login'))

    def test_user_cannot_access_admin_dashboard(self):
        self.client.force_login(self.viewer_user)
        response = self.client.get(reverse('admin_dashboard'))

        self.assertRedirects(response, reverse('login'))

    def test_staff_dashboard_renders_for_staff(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('staff_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/staff_dashboard.html')

    def test_admin_dashboard_renders_for_admin(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/admin_dashboard.html')
