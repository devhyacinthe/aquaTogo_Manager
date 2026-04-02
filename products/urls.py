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
    path("categories/", views.category_list, name="category_list"),
    path("categories/nouvelle/", views.category_create, name="category_create"),
    path("categories/<int:pk>/modifier/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/supprimer/", views.category_delete, name="category_delete"),
]
