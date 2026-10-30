"""Server-side authorization. Templates may hide links, but every protected view must use these."""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from apps.operators.models import Operator, OperatorMembership

from .models import User


def role_required(*roles):
    """Allow signed-in, active users whose role is listed. Platform admins always pass."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not (user.is_platform_admin or user.role in roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped

    return decorator


def memberships(user, **flags):
    return OperatorMembership.objects.filter(
        user=user, is_active=True, operator__is_active=True, user__role=User.Role.OPERATOR, **flags
    )


def operators_for(user):
    """Operators whose records this user may see."""
    if not user.is_authenticated:
        return Operator.objects.none()
    if user.is_platform_admin:
        return Operator.objects.all()
    return Operator.objects.filter(pk__in=memberships(user).values("operator"))


def can_edit_schedules(user, operator):
    if not user.is_authenticated:
        return False
    return user.is_platform_admin or memberships(user, operator=operator, can_edit_schedules=True).exists()


def can_view_manifest(user, schedule):
    if not user.is_authenticated:
        return False
    return user.is_platform_admin or memberships(
        user, operator_id=schedule.route.operator_id, can_view_manifests=True
    ).exists()
