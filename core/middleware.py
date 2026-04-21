from django.shortcuts import redirect
from django.urls import reverse


# URL prefixes an employee is allowed to access
_EMPLOYE_ALLOWED_PREFIXES = (
    "/prestations/",
    "/profil/",
    "/login/",
    "/logout/",
    "/static/",
    "/media/",
    "/admin/",  # keep admin accessible (Django will handle its own permission checks)
)


class RoleAccessMiddleware:
    """Restrict employees to services/execution pages only."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile = getattr(request.user, "profile", None)
            if profile and profile.is_employe:
                path = request.path
                allowed = any(path.startswith(p) for p in _EMPLOYE_ALLOWED_PREFIXES)
                if not allowed:
                    return redirect(reverse("services:execution_list"))
        return self.get_response(request)
