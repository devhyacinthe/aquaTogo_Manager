from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.AquaLoginView.as_view(), name="login"),
    path("logout/", views.AquaLogoutView.as_view(), name="logout"),
    path("profil/", views.profile, name="profile"),
    path("dashboard/chart-data/", views.dashboard_chart_data, name="dashboard_chart_data"),
    path("dashboard/telecharger/prestations-demain/", views.download_prestations_demain, name="download_prestations_demain"),
    path("dashboard/telecharger/ventes-aujourd-hui/", views.download_ventes_aujourd_hui, name="download_ventes_aujourd_hui"),
    path("employes/", views.employe_list, name="employe_list"),
    path("employes/creer/", views.employe_create, name="employe_create"),
    path("employes/<int:pk>/modifier/", views.employe_edit, name="employe_edit"),
    path("employes/<int:pk>/toggle/", views.employe_toggle, name="employe_toggle"),
    path("employes/<int:pk>/supprimer/", views.employe_delete, name="employe_delete"),
]
