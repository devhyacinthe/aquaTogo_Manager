from django.urls import path
from . import views

app_name = "products"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("nouveau/", views.product_create, name="create"),
    path("<int:pk>/", views.product_detail, name="detail"),
    path("<int:pk>/modifier/", views.product_edit, name="edit"),
    path("<int:pk>/supprimer/", views.product_delete, name="delete"),
    path("<int:pk>/stock/", views.product_adjust_stock, name="adjust_stock"),
]
