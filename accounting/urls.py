from django.urls import path
from . import views

app_name = "accounting"

urlpatterns = [
    path("", views.expense_list, name="list"),
    path("nouveau/", views.expense_create, name="create"),
    path("<int:pk>/modifier/", views.expense_edit, name="edit"),
    path("<int:pk>/supprimer/", views.expense_delete, name="delete"),
    path("rapport/", views.accounting_report, name="report"),
    path("rapport/pdf/", views.report_pdf, name="report_pdf"),
    path("export/excel/", views.expense_export_excel, name="export_excel"),
]
