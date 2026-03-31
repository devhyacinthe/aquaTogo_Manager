from django.urls import path
from . import views

app_name = "sales"

urlpatterns = [
    path("", views.sale_list, name="list"),
    path("nouvelle/", views.sale_create, name="create"),
    path("<int:pk>/", views.sale_detail, name="detail"),
    path("<int:pk>/paiement/", views.sale_add_payment, name="add_payment"),
    path("api/clients/", views.api_clients, name="api_clients"),
    path("api/produits/", views.api_products, name="api_products"),
    path("api/services/", views.api_services, name="api_services"),
]
