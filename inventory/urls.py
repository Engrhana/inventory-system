from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views


urlpatterns = [
    path('', views.root_redirect, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', views.user_dashboard, name='dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('staff-dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/new/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_update, name='category_update'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    path('inventory/new/', views.product_create, name='product_create'),
    path('inventory/<int:pk>/restock/', views.product_restock, name='product_restock'),
    path('inventory/<int:pk>/history/', views.product_stock_history, name='product_stock_history'),
    path('inventory/<int:pk>/edit/', views.product_update, name='product_update'),
    path('inventory/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('sales/', views.sales_list, name='sales_list'),
    path('sales/new/', views.sale_create, name='sale_create'),
    path('sales/<int:pk>/receipt/', views.sale_receipt, name='sale_receipt'),
    path('sales/<int:pk>/edit/', views.sale_update, name='sale_update'),
    path('sales/<int:pk>/delete/', views.sale_delete, name='sale_delete'),
    path('reports/', views.reports, name='reports'),
    path('reports/export/excel/', views.export_reports_excel, name='export_reports_excel'),
    path('reports/export/pdf/', views.export_reports_pdf, name='export_reports_pdf'),
    path(
        'forgot-password/',
        views.InventoryPasswordResetView.as_view(
            template_name='registration/forgot_password.html',
            email_template_name='registration/forgot_password_email.html',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='forgot_password',
    ),
    path(
        'forgot-password/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/forgot_password_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/forgot_password_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/forgot_password_complete.html',
        ),
        name='password_reset_complete',
    ),
]
