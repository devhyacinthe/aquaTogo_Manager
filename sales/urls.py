from django.urls import path
from . import views

app_name = "sales"

urlpatterns = [
    path("", views.sale_list, name="list"),
    path("nouvelle/", views.sale_create, name="create"),
    path("<int:pk>/", views.sale_detail, name="detail"),
    path("<int:pk>/paiement/", views.sale_add_payment, name="add_payment"),
    path("<int:pk>/annuler/", views.sale_cancel, name="cancel"),
    path("<int:pk>/modifier/", views.sale_modify, name="modify"),
    path("api/clients/", views.api_clients, name="api_clients"),
    path("api/clients/creer/", views.api_create_client, name="api_create_client"),
    path("api/produits/", views.api_products, name="api_products"),
    path("api/services/", views.api_services, name="api_services"),
    path("export/csv/", views.sale_export_csv, name="export_csv"),
    path("export/excel/", views.sale_export_excel, name="export_excel"),
    path("<int:pk>/facture.pdf", views.sale_invoice_pdf, name="invoice_pdf"),
]
