from django.urls import path
from . import views

app_name = "devis"

urlpatterns = [
    path("",                      views.quote_list,          name="list"),
    path("nouveau/",              views.quote_create,        name="create"),
    path("<int:pk>/",             views.quote_detail,        name="detail"),
    path("<int:pk>/statut/",      views.quote_update_status, name="update_status"),
    path("<int:pk>/convertir/",   views.quote_convert,       name="convert"),
    path("<int:pk>/devis.pdf",    views.quote_pdf,           name="pdf"),
]
