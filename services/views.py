from datetime import date as _date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ServiceForm
from .models import Service, ServiceExecution


@login_required
def service_list(request):
    services = Service.objects.filter(is_active=True).order_by("name")

    # Annotate execution count per service
    from django.db.models import Count
    services = services.annotate(execution_count=Count("executions"))

    upcoming_count = ServiceExecution.objects.filter(
        is_completed=False,
        next_due_date__isnull=False,
    ).count()

    context = {
        "services": services,
        "upcoming_count": upcoming_count,
        "is_staff": request.user.is_staff,
        "app_name": "services",
    }
    return render(request, "services/list.html", context)


@login_required
def service_create(request):
    if not request.user.is_staff:
        raise PermissionDenied

    if request.method == "POST":
        form = ServiceForm(request.POST)
        if form.is_valid():
            service = form.save()
            messages.success(request, f"Prestation « {service.name} » créée avec succès.")
            return redirect("services:detail", pk=service.pk)
    else:
        form = ServiceForm()

    context = {
        "form": form,
        "title": "Nouvelle prestation",
        "submit_label": "Créer la prestation",
        "app_name": "services",
    }
    return render(request, "services/form.html", context)


@login_required
def service_detail(request, pk):
    service = get_object_or_404(Service, pk=pk)

    executions = (
        ServiceExecution.objects
        .filter(service=service)
        .select_related("client")
        .order_by("-execution_date")[:15]
    )

    upcoming = (
        ServiceExecution.objects
        .filter(service=service, is_completed=False, next_due_date__isnull=False)
        .select_related("client")
        .order_by("next_due_date")
    )

    context = {
        "service": service,
        "executions": executions,
        "upcoming": upcoming,
        "is_staff": request.user.is_staff,
        "today": timezone.now().date(),
        "app_name": "services",
    }
    return render(request, "services/detail.html", context)


@login_required
def service_edit(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied

    service = get_object_or_404(Service, pk=pk)

    if request.method == "POST":
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, f"Prestation « {service.name} » mise à jour.")
            return redirect("services:detail", pk=service.pk)
    else:
        form = ServiceForm(instance=service)

    context = {
        "form": form,
        "service": service,
        "title": f"Modifier « {service.name} »",
        "submit_label": "Enregistrer les modifications",
        "app_name": "services",
    }
    return render(request, "services/form.html", context)


@login_required
@require_POST
def service_delete(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied

    service = get_object_or_404(Service, pk=pk)
    service.is_active = False
    service.save(update_fields=["is_active"])
    messages.success(request, f"Prestation « {service.name} » archivée.")
    return redirect("services:list")


@login_required
def execution_list(request):
    from datetime import timedelta
    today = timezone.now().date()
    periode = request.GET.get("periode", "week")

    qs = (
        ServiceExecution.objects
        .filter(is_completed=False, next_due_date__isnull=False)
        .select_related("client", "service")
        .order_by("next_due_date")
    )

    if periode == "today":
        qs = qs.filter(next_due_date__lte=today)
    elif periode == "all":
        pass  # tout afficher
    else:
        periode = "week"
        qs = qs.filter(next_due_date__lte=today + timedelta(days=6))

    context = {
        "executions": qs,
        "today": today,
        "periode": periode,
        "app_name": "services",
        "url_name": "execution_list",
    }
    return render(request, "services/execution_list.html", context)


@login_required
@require_POST
def record_execution(request, service_pk):
    """
    Enregistre une exécution de prestation + crée une vente + paiement optionnel.
    Appelé depuis le formulaire Alpine.js sur la page détail du service.
    """
    from clients.models import Client
    from sales.models import Payment, Sale, SaleItem

    service = get_object_or_404(Service, pk=service_pk, is_active=True)

    # ── Client ───────────────────────────────────────────────────────────────
    client_id = request.POST.get("client_id", "").strip()
    client = None
    if client_id:
        try:
            client = Client.objects.get(pk=int(client_id), is_active=True)
        except (Client.DoesNotExist, ValueError):
            client = None

    # ── Date d'exécution ─────────────────────────────────────────────────────
    raw_date = request.POST.get("execution_date", "").strip()
    try:
        exec_date = _date.fromisoformat(raw_date) if raw_date else _date.today()
    except ValueError:
        exec_date = _date.today()

    # ── Montant unitaire (modifiable sur le formulaire) ───────────────────────
    raw_price = request.POST.get("unit_price", "").strip()
    try:
        unit_price = Decimal(raw_price) if raw_price else service.price
        if unit_price <= 0:
            unit_price = service.price
    except InvalidOperation:
        unit_price = service.price

    # ── Paiement ─────────────────────────────────────────────────────────────
    raw_payment = request.POST.get("payment_amount", "").strip()
    payment_method = request.POST.get("payment_method", "cash")

    try:
        with transaction.atomic():
            # Vente
            sale = Sale.objects.create(
                client=client,
                created_by=request.user,
                sale_date=exec_date,
            )
            # Ligne de vente
            sale_item = SaleItem.objects.create(
                sale=sale,
                service=service,
                quantity=1,
                unit_price=unit_price,
                purchase_price_snapshot=Decimal("0.00"),
            )
            sale.recompute_totals()

            # Exécution liée
            ServiceExecution.objects.create(
                client=client,
                service=service,
                sale_item=sale_item,
                execution_date=exec_date,
            )

            # Paiement optionnel
            if raw_payment:
                try:
                    amount = Decimal(raw_payment)
                    if 0 < amount:
                        amount = min(amount, sale.total_amount)
                        valid_methods = [m[0] for m in Payment.Method.choices]
                        if payment_method not in valid_methods:
                            payment_method = "cash"
                        Payment.objects.create(
                            sale=sale,
                            recorded_by=request.user,
                            amount=amount,
                            payment_method=payment_method,
                            payment_date=exec_date,
                        )
                except InvalidOperation:
                    pass

        client_label = client.name if client else "client anonyme"
        messages.success(request, f"Exécution de « {service.name} » pour {client_label} enregistrée.")
    except Exception as e:
        messages.error(request, f"Erreur : {e}")

    return redirect("services:detail", pk=service_pk)


@login_required
@require_POST
def execution_complete(request, pk):
    execution = get_object_or_404(ServiceExecution, pk=pk)
    execution.is_completed = True
    execution.save(update_fields=["is_completed"])
    messages.success(
        request,
        f"Prestation « {execution.service.name} » pour {execution.client.name} marquée comme effectuée."
    )
    next_url = request.POST.get("next", "")
    if next_url:
        return redirect(next_url)
    return redirect("services:execution_list")
