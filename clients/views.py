import re
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Value, DecimalField, F, ExpressionWrapper
from django.db.models.functions import Coalesce

from .models import Client
from .forms import ClientForm


def _annotate_clients(qs):
    """Annotate a Client queryset with ann_total, ann_paid, ann_balance."""
    return qs.annotate(
        ann_total=Coalesce(
            Sum("sales__total_amount", distinct=True),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        ann_paid=Coalesce(
            Sum("sales__payments__amount"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    ).annotate(
        ann_balance=ExpressionWrapper(
            F("ann_total") - F("ann_paid"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )


@login_required
def client_list(request):
    q = request.GET.get("q", "").strip()
    filtre = request.GET.get("filtre", "all")

    base_qs = Client.objects.filter(is_active=True)
    if q:
        base_qs = base_qs.filter(Q(name__icontains=q) | Q(phone__icontains=q))

    clients = _annotate_clients(base_qs)

    if filtre == "debtors":
        clients = clients.filter(ann_balance__gt=0).order_by("-ann_balance")
    else:
        clients = clients.order_by("name")

    total_count = Client.objects.filter(is_active=True).count()
    debtors_count = (
        _annotate_clients(Client.objects.filter(is_active=True))
        .filter(ann_balance__gt=0)
        .count()
    )

    context = {
        "clients": clients,
        "q": q,
        "filtre": filtre,
        "total_count": total_count,
        "debtors_count": debtors_count,
        "is_staff": request.user.is_staff,
        "app_name": "clients",
    }
    return render(request, "clients/list.html", context)


@login_required
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, f"Client « {client.name} » ajouté avec succès.")
            return redirect("clients:detail", pk=client.pk)
    else:
        form = ClientForm()

    context = {
        "form": form,
        "title": "Nouveau client",
        "submit_label": "Créer le client",
        "app_name": "clients",
    }
    return render(request, "clients/form.html", context)


@login_required
def client_detail(request, pk):
    from services.models import ServiceExecution

    client = get_object_or_404(Client, pk=pk)

    sales = (
        client.sales
        .select_related("created_by")
        .prefetch_related("items__product", "items__service", "payments")
        .order_by("-sale_date", "-id")[:20]
    )

    service_executions = (
        ServiceExecution.objects
        .filter(client=client)
        .select_related("service")
        .order_by("-execution_date")[:10]
    )

    upcoming = client.upcoming_service_executions(days=30)
    phone_digits = re.sub(r"\D", "", client.phone) if client.phone else ""

    context = {
        "client": client,
        "sales": sales,
        "service_executions": service_executions,
        "upcoming": upcoming,
        "phone_digits": phone_digits,
        "is_staff": request.user.is_staff,
        "app_name": "clients",
    }
    return render(request, "clients/detail.html", context)


@login_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)

    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f"Client « {client.name} » mis à jour.")
            return redirect("clients:detail", pk=client.pk)
    else:
        form = ClientForm(instance=client)

    context = {
        "form": form,
        "client": client,
        "title": f"Modifier « {client.name} »",
        "submit_label": "Enregistrer les modifications",
        "app_name": "clients",
    }
    return render(request, "clients/form.html", context)
