from django.shortcuts import redirect
from django.urls import reverse

# Préfixes autorisés pour un employé
_EMPLOYE_ALLOWED_PREFIXES = (
    "/ventes/",
    "/produits/",
    "/clients/",
    "/prestations/",
    "/profil/",
    "/login/",
    "/logout/",
    "/static/",
    "/media/",
    "/admin/",
)

# Actions produit interdites aux employés (modification de stock / catalogue)
_EMPLOYE_BLOCKED_SUFFIXES = (
    "/stock/",
    "/supprimer/",
    "/modifier/",
    "/desarchiver/",
    "archives/",
    "/categories/",
    "nouveau/",
)


class RoleAccessMiddleware:
    """Restreint les employés aux sections autorisées."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile = getattr(request.user, "profile", None)
            if profile and profile.is_employe:
                path = request.path

                # Vérifier les préfixes autorisés
                if not any(path.startswith(p) for p in _EMPLOYE_ALLOWED_PREFIXES):
                    return redirect(reverse("sales:list"))

                # Bloquer les actions de modification de stock/catalogue produits
                if path.startswith("/produits/") and any(
                    path.endswith(s) or s in path for s in _EMPLOYE_BLOCKED_SUFFIXES
                ):
                    return redirect(reverse("products:list"))

        return self.get_response(request)
