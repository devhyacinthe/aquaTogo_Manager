from django.urls import path
from . import views

app_name = "clients"

urlpatterns = [
    path("", views.client_list, name="list"),
    path("nouveau/", views.client_create, name="create"),
    path("<int:pk>/", views.client_detail, name="detail"),
    path("<int:pk>/modifier/", views.client_edit, name="edit"),
    path("<int:pk>/solder/", views.client_settle_debt, name="settle_debt"),
]
