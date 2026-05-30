from .access import can_export, can_manage_inventory, get_dashboard_url, get_role_label, is_admin_user, is_staff_user, is_standard_user


def access_context(request):
    user = request.user
    return {
        'is_admin_user': is_admin_user(user),
        'is_staff_user': is_staff_user(user),
        'is_standard_user': is_standard_user(user),
        'can_manage_inventory': can_manage_inventory(user),
        'can_export_reports': can_export(user),
        'user_role_label': get_role_label(user),
        'current_dashboard_url': get_dashboard_url(user),
    }
