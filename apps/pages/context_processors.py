from django.conf import settings

from apps.compliance.models import PolicyVersion

PLATFORM_ROLES = {
    "intermediary": "a booking intermediary",
    "marketplace": "a marketplace",
    "operator": "the transport operator",
}


def site(request):
    return {
        "business": settings.BUSINESS,
        "platform_role_label": PLATFORM_ROLES.get(settings.BUSINESS["platform_role"], ""),
        "policy_types": PolicyVersion.PolicyType.choices,
    }
