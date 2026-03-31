from django.urls import path
from . import views

app_name = "services"

urlpatterns = [
    path("", views.service_list, name="list"),
    path("nouveau/", views.service_create, name="create"),
    path("<int:pk>/", views.service_detail, name="detail"),
    path("<int:pk>/modifier/", views.service_edit, name="edit"),
    path("<int:pk>/supprimer/", views.service_delete, name="delete"),
    path("executions/", views.execution_list, name="execution_list"),
    path("executions/<int:pk>/completer/", views.execution_complete, name="execution_complete"),
    path("<int:service_pk>/executer/", views.record_execution, name="record_execution"),
]
