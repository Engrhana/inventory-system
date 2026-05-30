from django.urls import reverse


def is_admin_user(user):
    return bool(getattr(user, 'is_authenticated', False) and user.is_superuser)


def is_staff_user(user):
    return bool(getattr(user, 'is_authenticated', False) and user.is_staff and not user.is_superuser)


def is_standard_user(user):
    return bool(getattr(user, 'is_authenticated', False) and not user.is_staff and not user.is_superuser)


def can_manage_inventory(user):
    return bool(getattr(user, 'is_authenticated', False) and (user.is_superuser or user.is_staff))


def can_export(user):
    return can_manage_inventory(user)


def get_role_label(user):
    if not getattr(user, 'is_authenticated', False):
        return 'Guest'
    if is_admin_user(user):
        return 'Admin'
    if is_staff_user(user):
        return 'Staff'
    return 'User'


def get_dashboard_url(user):
    if is_admin_user(user):
        return reverse('staff_dashboard')
    if is_staff_user(user):
        return reverse('staff_dashboard')
    if is_standard_user(user):
        return reverse('dashboard')
    return reverse('login')
