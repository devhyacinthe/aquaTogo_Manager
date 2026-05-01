import calendar as _cal
from collections import defaultdict
from datetime import date as _date, timedelta
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
    from django.db.models import Prefetch

    service = get_object_or_404(Service, pk=pk)

    # Récupère les exécutions « têtes de groupe » (sans parent) + leurs enfants
    # Exclut les exécutions liées à une vente annulée
    head_execs = list(
        ServiceExecution.objects
        .filter(service=service, parent_execution__isnull=True)
        .exclude(sale_item__sale__status="canceled")
        .select_related("client", "sale_item__sale")
        .prefetch_related(
            Prefetch(
                "children",
                queryset=ServiceExecution.objects.order_by("execution_date"),
            )
        )
        .order_by("-execution_date")[:10]
    )

    # Construit les groupes pour le template
    execution_groups = []
    for head in head_execs:
        children = list(head.children.all())
        members = [head] + children
        all_done = all(m.is_completed for m in members)
        any_done = any(m.is_completed for m in members)
        execution_groups.append({
            "head": head,
            "members": members,
            "children": children,
            "is_group": bool(children),
            "all_done": all_done,
            "any_done": any_done,
        })

    upcoming = (
        ServiceExecution.objects
        .filter(service=service, is_completed=False, next_due_date__isnull=False)
        .select_related("client")
        .order_by("next_due_date")
    )

    context = {
        "service": service,
        "execution_groups": execution_groups,
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


_MONTHS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]
_DAYS_FR_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
_DAYS_FR_LONG = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _parse_date(raw: str) -> _date:
    try:
        return _date.fromisoformat(raw)
    except (ValueError, TypeError):
        return timezone.now().date()


@login_required
def calendar_week(request):
    ref = _parse_date(request.GET.get("date", ""))
    week_start = ref - timedelta(days=ref.weekday())  # Monday
    week_end = week_start + timedelta(days=6)

    executions = (
        ServiceExecution.objects
        .filter(next_due_date__gte=week_start, next_due_date__lte=week_end)
        .select_related("client", "service")
        .order_by("scheduled_time", "client__name")
    )

    by_date = defaultdict(list)
    for ex in executions:
        by_date[ex.next_due_date].append(ex)

    week_days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        week_days.append({
            "date": d,
            "label_short": _DAYS_FR_SHORT[i],
            "label_long": _DAYS_FR_LONG[i],
            "executions": by_date.get(d, []),
        })

    context = {
        "week_days": week_days,
        "week_start": week_start,
        "week_end": week_end,
        "prev_week": (week_start - timedelta(days=7)).isoformat(),
        "next_week": (week_start + timedelta(days=7)).isoformat(),
        "today": timezone.now().date(),
        "app_name": "services",
    }
    return render(request, "services/calendar_week.html", context)


@login_required
def calendar_month(request):
    ref = _parse_date(request.GET.get("date", ""))
    year, month = ref.year, ref.month
    today = timezone.now().date()

    first_day = _date(year, month, 1)
    last_day = _date(year, month, _cal.monthrange(year, month)[1])

    executions = (
        ServiceExecution.objects
        .filter(next_due_date__gte=first_day, next_due_date__lte=last_day)
        .select_related("client", "service")
    )

    by_day = defaultdict(list)
    for ex in executions:
        by_day[ex.next_due_date.day].append(ex)

    # Build grid: list of weeks, each week = list of 7 cells (None = padding)
    weeks = []
    for week in _cal.monthcalendar(year, month):
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(None)
            else:
                d = _date(year, month, day_num)
                execs = by_day.get(day_num, [])
                row.append({
                    "date": d,
                    "day": day_num,
                    "executions": execs[:3],
                    "extra": max(0, len(execs) - 3),
                })
        weeks.append(row)

    # Prev / next month navigation
    if month == 1:
        prev_ref = _date(year - 1, 12, 1)
    else:
        prev_ref = _date(year, month - 1, 1)
    if month == 12:
        next_ref = _date(year + 1, 1, 1)
    else:
        next_ref = _date(year, month + 1, 1)

    context = {
        "weeks": weeks,
        "year": year,
        "month_name": _MONTHS_FR[month - 1],
        "day_headers": _DAYS_FR_SHORT,
        "prev_month": prev_ref.isoformat(),
        "next_month": next_ref.isoformat(),
        "today": today,
        "app_name": "services",
    }
    return render(request, "services/calendar_month.html", context)


@login_required
def calendar_day(request):
    selected = _parse_date(request.GET.get("date", ""))
    today = timezone.now().date()

    executions = (
        ServiceExecution.objects
        .filter(next_due_date=selected)
        .select_related("client", "service")
        .order_by("scheduled_time", "client__name")
    )

    context = {
        "selected_date": selected,
        "day_label": _DAYS_FR_LONG[selected.weekday()],
        "executions": executions,
        "prev_day": (selected - timedelta(days=1)).isoformat(),
        "next_day": (selected + timedelta(days=1)).isoformat(),
        "today": today,
        "app_name": "services",
    }
    return render(request, "services/calendar_day.html", context)


@login_required
@require_POST
def execution_confirm(request, pk):
    execution = get_object_or_404(ServiceExecution, pk=pk)
    execution.confirmed = not execution.confirmed
    execution.save(update_fields=["confirmed"])
    next_url = request.POST.get("next", "")
    if next_url:
        return redirect(next_url)
    return redirect("services:calendar_week")


@login_required
@require_POST
def execution_complete(request, pk):
    execution = get_object_or_404(ServiceExecution, pk=pk)
    if not execution.is_completed:
        execution.is_completed = True
        execution.save(update_fields=["is_completed"])

        # Auto-planification du prochain tour pour les services récurrents
        if execution.next_due_date and execution.tours_per_month:
            next_date = execution.next_due_date
            already_exists = ServiceExecution.objects.filter(
                client=execution.client,
                service=execution.service,
                execution_date=next_date,
                is_completed=False,
            ).exists()
            if not already_exists:
                ServiceExecution.objects.create(
                    client=execution.client,
                    service=execution.service,
                    tours_per_month=execution.tours_per_month,
                    execution_date=next_date,
                )
                messages.success(
                    request,
                    f"Prestation « {execution.service.name} » pour {execution.client.name} effectuée. "
                    f"Prochain passage planifié le {next_date.strftime('%d/%m/%Y')}."
                )
            else:
                messages.success(
                    request,
                    f"Prestation « {execution.service.name} » pour {execution.client.name} marquée comme effectuée."
                )
        else:
            messages.success(
                request,
                f"Prestation « {execution.service.name} » pour {execution.client.name} marquée comme effectuée."
            )

    next_url = request.POST.get("next", "")
    if next_url:
        return redirect(next_url)
    return redirect("services:execution_list")
