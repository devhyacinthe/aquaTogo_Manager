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
]
