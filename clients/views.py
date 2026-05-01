import re
from datetime import date as _date
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Value, DecimalField, F, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.views.decorators.http import require_POST

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
        "today": _date.today(),
        "is_staff": request.user.is_staff,
        "app_name": "clients",
    }
    return render(request, "clients/detail.html", context)


@login_required
@require_POST
def client_settle_debt(request, pk):
    """
    Distribue un paiement sur les ventes impayées/partielles du client,
    des plus anciennes aux plus récentes.
    """
    from sales.models import Payment

    client = get_object_or_404(Client, pk=pk)

    # ── Montant ───────────────────────────────────────────────────────────────
    try:
        amount = Decimal(request.POST.get("amount", "0").strip())
    except InvalidOperation:
        amount = Decimal("0")

    if amount <= 0:
        messages.error(request, "Le montant doit être supérieur à 0.")
        return redirect("clients:detail", pk=pk)

    balance = client.outstanding_balance
    if amount > balance:
        messages.error(
            request,
            f"Le montant ({amount:,.0f} FCFA) dépasse le solde dû ({balance:,.0f} FCFA)."
        )
        return redirect("clients:detail", pk=pk)

    # ── Méthode & date ────────────────────────────────────────────────────────
    payment_method = request.POST.get("payment_method", "cash")
    valid_methods = [m[0] for m in Payment.Method.choices]
    if payment_method not in valid_methods:
        payment_method = "cash"

    raw_date = request.POST.get("payment_date", "").strip()
    try:
        pay_date = _date.fromisoformat(raw_date) if raw_date else _date.today()
    except ValueError:
        pay_date = _date.today()

    # ── Distribution sur les ventes impayées (plus anciennes en premier) ──────
    unpaid_sales = (
        client.sales
        .filter(payment_status__in=["unpaid", "partial"])
        .order_by("sale_date", "id")
    )

    remaining = amount
    payments_created = 0

    try:
        with transaction.atomic():
            for sale in unpaid_sales:
                if remaining <= 0:
                    break
                to_pay = min(remaining, sale.remaining_balance)
                if to_pay > 0:
                    Payment.objects.create(
                        sale=sale,
                        recorded_by=request.user,
                        amount=to_pay,
                        payment_method=payment_method,
                        payment_date=pay_date,
                    )
                    remaining -= to_pay
                    payments_created += 1

        messages.success(
            request,
            f"{amount:,.0f} FCFA encaissés sur {payments_created} vente{'' if payments_created == 1 else 's'}."
        )
    except Exception as e:
        messages.error(request, f"Erreur lors de l'enregistrement : {e}")

    return redirect("clients:detail", pk=pk)


@login_required
@require_POST
def client_delete(request, pk):
    if not request.user.is_staff:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    client = get_object_or_404(Client, pk=pk)
    name = client.name
    client.is_active = False
    client.save(update_fields=["is_active"])
    messages.success(request, f"Client « {name} » supprimé.")
    return redirect("clients:list")


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
