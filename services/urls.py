from django.urls import path
from . import views

app_name = "services"

urlpatterns = [
    path("", views.service_list, name="list"),
    path("nouveau/", views.service_create, name="create"),
    path("<int:pk>/", views.service_detail, name="detail"),
    path("<int:pk>/modifier/", views.service_edit, name="edit"),
    path("<int:pk>/supprimer/", views.service_delete, name="delete"),
    path("<int:pk>/assigner-rapide/", views.service_quick_assign, name="quick_assign"),
    path("assigner/", views.service_assign, name="assign"),
    path("executions/", views.execution_list, name="execution_list"),
    path("executions/<int:pk>/completer/", views.execution_complete, name="execution_complete"),
    path("executions/<int:pk>/confirmer/", views.execution_confirm, name="execution_confirm"),
    path("executions/<int:pk>/encaisser/", views.execution_collect_payment, name="execution_collect"),
    path("executions/<int:pk>/masquer/", views.execution_hide, name="execution_hide"),
    path("executions/<int:pk>/facture/", views.execution_invoice, name="execution_invoice"),
    path("executions/calendrier/", views.calendar_week, name="calendar_week"),
    path("executions/calendrier/semaine/", views.calendar_week, name="calendar_week_filter"),
    path("executions/calendrier/mois/", views.calendar_month, name="calendar_month"),
    path("executions/calendrier/jour/", views.calendar_day, name="calendar_day"),
    path("<int:service_pk>/executer/", views.record_execution, name="record_execution"),
    # Tâches
    path("taches/", views.task_list, name="task_list"),
    path("taches/nouvelle/", views.task_create, name="task_create"),
    path("taches/<int:pk>/", views.task_detail, name="task_detail"),
    path("taches/<int:pk>/completer/", views.task_complete, name="task_complete"),
    path("taches/<int:pk>/supprimer/", views.task_delete, name="task_delete"),
    path("taches/<int:pk>/vente/",     views.task_to_sale, name="task_to_sale"),
]
