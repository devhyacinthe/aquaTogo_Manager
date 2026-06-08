import calendar as _cal
from collections import defaultdict
from datetime import date as _date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ServiceForm
from .models import Service, ServiceExecution, Task, TaskProduct


def _assign_tour_numbers(execution_list: list) -> None:
    """Attribue `tour_number` à chaque exécution.
    Priorité : start_tour si renseigné, sinon position parmi les frères (anciennes données).
    """
    children_without_start = [
        ex for ex in execution_list
        if ex.start_tour is None and ex.parent_execution_id
    ]
    position_map: dict = {}
    if children_without_start:
        parent_ids = {ex.parent_execution_id for ex in children_without_start}
        rows = (
            ServiceExecution.objects
            .filter(parent_execution_id__in=parent_ids)
            .order_by("execution_date")
            .values("id", "parent_execution_id")
        )
        groups: dict = {}
        for row in rows:
            groups.setdefault(row["parent_execution_id"], []).append(row["id"])
        for pid, ids in groups.items():
            for i, cid in enumerate(ids):
                position_map[(pid, cid)] = i + 2  # premier enfant = Tour 2

    for ex in execution_list:
        if ex.start_tour:
            ex.tour_number = ex.start_tour
        elif ex.parent_execution_id:
            ex.tour_number = position_map.get((ex.parent_execution_id, ex.id), 2)
        else:
            ex.tour_number = 1


@login_required
def service_list(request):
    import json as _json
    services = Service.objects.filter(is_active=True).order_by("name")

    # Annotate execution count per service
    from django.db.models import Count
    services = services.annotate(execution_count=Count("executions"))

    upcoming_count = ServiceExecution.objects.filter(
        is_completed=False,
        next_due_date__isnull=False,
    ).count()

    # Données JSON pour le modal Alpine.js d'assignation rapide
    services_json = _json.dumps([
        {"id": s.id, "name": s.name, "price": str(s.price)}
        for s in services
    ])

    context = {
        "services": services,
        "services_json": services_json,
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
        _assign_tour_numbers(members)
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

    upcoming_list = list(
        ServiceExecution.objects
        .filter(service=service, is_completed=False, next_due_date__isnull=False)
        .select_related("client")
        .order_by("next_due_date")
    )
    _assign_tour_numbers(upcoming_list)

    context = {
        "service": service,
        "execution_groups": execution_groups,
        "upcoming": upcoming_list,
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
@require_POST
def service_quick_assign(request, pk):
    """Assignation rapide : crée Sale (impayé) + SaleItem + Executions planifiées."""
    from clients.models import Client
    from sales.models import Sale, SaleItem

    service = get_object_or_404(Service, pk=pk, is_active=True)

    client_id = request.POST.get("client_id", "").strip()
    tours_raw = request.POST.get("tours_per_month", "").strip()
    start_tour_raw = request.POST.get("start_tour", "1").strip()

    # Client obligatoire
    client = None
    if client_id:
        try:
            client = Client.objects.get(pk=int(client_id), is_active=True)
        except (Client.DoesNotExist, ValueError):
            client = None

    if not client:
        messages.error(request, "Veuillez sélectionner un client valide.")
        return redirect("services:list")

    # Vérifier si le client est déjà programmé pour cette prestation
    existing = ServiceExecution.objects.filter(
        client=client,
        service=service,
        is_completed=False,
    ).exists()
    if existing:
        messages.error(
            request,
            f"« {client.name} » a déjà une prestation « {service.name} » en cours. "
            f"Terminez les tours en cours avant de réassigner.",
        )
        return redirect("services:list")

    tours_per_month = None
    if tours_raw:
        try:
            tours_per_month = int(tours_raw)
            if tours_per_month not in (1, 2, 3, 4):
                tours_per_month = None
        except ValueError:
            tours_per_month = None

    # Tour de départ choisi par l'utilisateur
    start_tour = 1
    try:
        start_tour = max(1, int(start_tour_raw))
        if tours_per_month and start_tour > tours_per_month:
            start_tour = 1
    except (ValueError, TypeError):
        start_tour = 1

    try:
        with transaction.atomic():
            # Vente (impayée)
            sale = Sale.objects.create(
                client=client,
                created_by=request.user,
                sale_date=_date.today(),
            )
            sale_item = SaleItem.objects.create(
                sale=sale,
                service=service,
                quantity=tours_per_month or 1,
                unit_price=service.price,
                purchase_price_snapshot=Decimal("0.00"),
            )
            sale.recompute_totals()

            # Premier passage
            first_exec = ServiceExecution.objects.create(
                client=client,
                service=service,
                sale_item=sale_item,
                execution_date=_date.today(),
                next_due_date=_date.today(),
                tours_per_month=tours_per_month,
                start_tour=start_tour,
            )

            # Passages suivants si multi-tours
            if tours_per_month and tours_per_month > 1:
                interval = first_exec.interval_days() or 0
                prev_date = _date.today()
                for i in range(1, tours_per_month):
                    raw_date = prev_date + timedelta(days=interval)
                    offset = (_date.today().weekday() - raw_date.weekday()) % 7
                    child_date = raw_date + timedelta(days=offset)
                    prev_date = child_date
                    child_tour = i + 1
                    ServiceExecution.objects.create(
                        client=client,
                        service=service,
                        tours_per_month=tours_per_month,
                        execution_date=child_date,
                        next_due_date=child_date,
                        parent_execution=first_exec,
                        start_tour=child_tour,
                    )

        freq_label = f" ({tours_per_month} tours/mois)" if tours_per_month else " (ponctuel)"
        messages.success(
            request,
            f"« {service.name} »{freq_label} assignée à {client.name}. Vente enregistrée (impayée).",
        )
    except Exception as e:
        messages.error(request, f"Erreur : {e}")

    return redirect("services:list")


@login_required
def execution_list(request):
    from datetime import timedelta
    today = timezone.now().date()
    periode = request.GET.get("periode", "week")

    ex_qs = (
        ServiceExecution.objects
        .filter(is_completed=False, next_due_date__isnull=False)
        .select_related("client", "service", "sale_item__sale")
        .order_by("next_due_date")
    )
    task_qs = (
        Task.objects
        .filter(is_completed=False)
        .select_related("client")
        .prefetch_related("task_products__product")
        .order_by("task_date")
    )

    if periode == "today":
        ex_qs   = ex_qs.filter(next_due_date__lte=today)
        task_qs = task_qs.filter(task_date__lte=today)
    elif periode == "all":
        pass
    else:
        periode = "week"
        ex_qs   = ex_qs.filter(next_due_date__lte=today + timedelta(days=6))
        task_qs = task_qs.filter(task_date__lte=today + timedelta(days=6))

    executions = list(ex_qs)
    _assign_tour_numbers(executions)

    # Liste unifiée triée par date pour l'affichage
    items = []
    for ex in executions:
        items.append({"type": "execution", "obj": ex, "date": ex.next_due_date})
    for task in task_qs:
        items.append({"type": "task", "obj": task, "date": task.task_date})
    items.sort(key=lambda x: x["date"])

    context = {
        "items": items,
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

    # Vérifier doublon client-service
    if client:
        existing = ServiceExecution.objects.filter(
            client=client, service=service, is_completed=False,
        ).exists()
        if existing:
            messages.error(
                request,
                f"« {client.name} » est déjà programmé(e) pour « {service.name} ». "
                f"Terminez les tours en cours avant de réassigner.",
            )
            return redirect("services:detail", pk=service_pk)

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

    executions = list(
        ServiceExecution.objects
        .filter(next_due_date__gte=week_start, next_due_date__lte=week_end,
                hidden_from_calendar=False)
        .select_related("client", "service")
        .order_by("scheduled_time", "client__name")
    )
    _assign_tour_numbers(executions)

    tasks = list(
        Task.objects
        .filter(task_date__gte=week_start, task_date__lte=week_end, is_completed=False)
        .select_related("client")
        .prefetch_related("task_products__product")
        .order_by("client__name")
    )

    by_date = defaultdict(list)
    for ex in executions:
        by_date[ex.next_due_date].append(ex)

    tasks_by_date = defaultdict(list)
    for task in tasks:
        tasks_by_date[task.task_date].append(task)

    week_days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        week_days.append({
            "date": d,
            "label_short": _DAYS_FR_SHORT[i],
            "label_long": _DAYS_FR_LONG[i],
            "executions": by_date.get(d, []),
            "tasks": tasks_by_date.get(d, []),
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

    executions = list(
        ServiceExecution.objects
        .filter(next_due_date__gte=first_day, next_due_date__lte=last_day,
                hidden_from_calendar=False)
        .select_related("client", "service")
    )
    _assign_tour_numbers(executions)

    tasks = list(
        Task.objects
        .filter(task_date__gte=first_day, task_date__lte=last_day, is_completed=False)
        .select_related("client")
        .order_by("task_date")
    )

    by_day = defaultdict(list)
    for ex in executions:
        by_day[ex.next_due_date.day].append(ex)

    tasks_by_day = defaultdict(list)
    for task in tasks:
        tasks_by_day[task.task_date.day].append(task)

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
                day_tasks = tasks_by_day.get(day_num, [])
                # Merge for display: prestations d'abord, tâches ensuite
                all_items = (
                    [{"type": "execution", "obj": ex} for ex in execs]
                    + [{"type": "task", "obj": t} for t in day_tasks]
                )
                row.append({
                    "date": d,
                    "day": day_num,
                    "items": all_items[:3],
                    "extra": max(0, len(all_items) - 3),
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

    executions = list(
        ServiceExecution.objects
        .filter(next_due_date=selected, hidden_from_calendar=False)
        .select_related("client", "service", "sale_item__sale")
        .order_by("scheduled_time", "client__name")
    )
    _assign_tour_numbers(executions)

    tasks = list(
        Task.objects
        .filter(task_date=selected, is_completed=False)
        .select_related("client")
        .prefetch_related("task_products__product")
        .order_by("client__name")
    )

    context = {
        "selected_date": selected,
        "day_label": _DAYS_FR_LONG[selected.weekday()],
        "executions": executions,
        "tasks": tasks,
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
        execution.completed_at = _date.today()
        execution.save(update_fields=["is_completed", "completed_at"])

        # Auto-planification du prochain tour pour les services récurrents
        if execution.next_due_date and execution.tours_per_month:
            interval = execution.interval_days() or 0

            # Des tours futurs existent-ils déjà ? (enfants directs ou frères plus tardifs)
            has_pending_future = (
                execution.children.filter(is_completed=False).exists()
                or (
                    execution.parent_execution_id
                    and ServiceExecution.objects.filter(
                        parent_execution_id=execution.parent_execution_id,
                        is_completed=False,
                        execution_date__gt=execution.execution_date,
                    ).exists()
                )
            )

            if not has_pending_future and interval:
                # Nouveau modèle : next_due_date == execution_date (today = date planifiée)
                # Ancien modèle : next_due_date = execution_date + interval (prochaine échéance)
                if execution.next_due_date == execution.execution_date:
                    next_exec_date = execution.execution_date + timedelta(days=interval)
                else:
                    next_exec_date = execution.next_due_date

                next_start_tour = None
                if execution.start_tour and execution.tours_per_month:
                    next_start_tour = (execution.start_tour % execution.tours_per_month) + 1

                # Créer automatiquement une vente (impayée) pour le prochain tour
                from sales.models import Sale, SaleItem

                with transaction.atomic():
                    sale = Sale.objects.create(
                        client=execution.client,
                        created_by=request.user,
                        sale_date=next_exec_date,
                    )
                    sale_item = SaleItem.objects.create(
                        sale=sale,
                        service=execution.service,
                        quantity=1,
                        unit_price=execution.service.price,
                        purchase_price_snapshot=Decimal("0.00"),
                    )
                    sale.recompute_totals()

                    new_exec = ServiceExecution.objects.create(
                        client=execution.client,
                        service=execution.service,
                        sale_item=sale_item,
                        tours_per_month=execution.tours_per_month,
                        execution_date=next_exec_date,
                        next_due_date=next_exec_date,
                        start_tour=next_start_tour,
                    )

                tour_label = f" (Tour {next_start_tour})" if next_start_tour else ""
                messages.success(
                    request,
                    f"Prestation « {execution.service.name} » pour {execution.client.name} effectuée. "
                    f"Prochain passage{tour_label} planifié le {next_exec_date.strftime('%d/%m/%Y')} "
                    f"— vente de {execution.service.price:,.0f} FCFA enregistrée (impayée)."
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


@login_required
@require_POST
def execution_collect_payment(request, pk):
    """Encaisser le paiement d'une exécution depuis le calendrier/liste.
    Crée un Payment sur la Sale liée."""
    from sales.models import Payment

    execution = get_object_or_404(
        ServiceExecution.objects.select_related("sale_item__sale", "client", "service"),
        pk=pk,
    )

    if not execution.sale_item or not execution.sale_item.sale:
        messages.error(request, "Aucune vente associée à cette exécution.")
        next_url = request.POST.get("next", "")
        return redirect(next_url or "services:execution_list")

    sale = execution.sale_item.sale

    raw_amount = request.POST.get("payment_amount", "").strip()
    payment_method = request.POST.get("payment_method", "cash")

    try:
        amount = Decimal(raw_amount) if raw_amount else sale.remaining_balance
        if amount <= 0:
            amount = sale.remaining_balance
    except InvalidOperation:
        amount = sale.remaining_balance

    if amount <= 0:
        messages.info(request, "Cette vente est déjà entièrement payée.")
        next_url = request.POST.get("next", "")
        return redirect(next_url or "services:execution_list")

    # Plafonner au solde restant
    amount = min(amount, sale.remaining_balance)

    valid_methods = [m[0] for m in Payment.Method.choices]
    if payment_method not in valid_methods:
        payment_method = "cash"

    Payment.objects.create(
        sale=sale,
        recorded_by=request.user,
        amount=amount,
        payment_method=payment_method,
        payment_date=_date.today(),
    )

    client_label = execution.client.name if execution.client else "client"
    messages.success(
        request,
        f"Paiement de {amount:,.0f} FCFA encaissé pour « {execution.service.name} » — {client_label}.",
    )

    next_url = request.POST.get("next", "")
    if next_url:
        return redirect(next_url)
    return redirect("services:execution_list")


@login_required
@require_POST
def execution_hide(request, pk):
    """Masquer/afficher une exécution dans le calendrier sans la supprimer."""
    execution = get_object_or_404(ServiceExecution, pk=pk)
    execution.hidden_from_calendar = not execution.hidden_from_calendar
    execution.save(update_fields=["hidden_from_calendar"])
    if execution.hidden_from_calendar:
        messages.success(request, f"Prestation retirée du calendrier.")
    else:
        messages.success(request, f"Prestation réaffichée dans le calendrier.")
    next_url = request.POST.get("next", "")
    if next_url:
        return redirect(next_url)
    return redirect("services:execution_list")


@login_required
def execution_invoice(request, pk):
    """Redirige vers la facture PDF de la vente liée à cette exécution."""
    execution = get_object_or_404(
        ServiceExecution.objects.select_related("sale_item__sale"),
        pk=pk,
    )
    if not execution.sale_item or not execution.sale_item.sale:
        messages.error(request, "Aucune vente associée à cette prestation.")
        return redirect("services:detail", pk=execution.service_id)
    return redirect("sales:invoice_pdf", pk=execution.sale_item.sale.pk)


# ── Tâches ────────────────────────────────────────────────────────────────────

@login_required
def task_list(request):
    from clients.models import Client as _Client
    filtre = request.GET.get("filtre", "pending")
    client_id = request.GET.get("client", "")

    qs = Task.objects.select_related("client").prefetch_related("task_products__product")
    if filtre == "done":
        qs = qs.filter(is_completed=True)
    elif filtre == "overdue":
        qs = qs.filter(is_completed=False, task_date__lt=timezone.now().date())
    else:
        qs = qs.filter(is_completed=False)

    if client_id:
        qs = qs.filter(client_id=client_id)

    clients = _Client.objects.filter(is_active=True).order_by("name")
    counts = {
        "pending": Task.objects.filter(is_completed=False).count(),
        "overdue": Task.objects.filter(is_completed=False, task_date__lt=timezone.now().date()).count(),
        "done":    Task.objects.filter(is_completed=True).count(),
    }
    return render(request, "services/task_list.html", {
        "tasks": qs,
        "filtre": filtre,
        "client_filter": client_id,
        "clients": clients,
        "counts": counts,
    })


@login_required
def task_create(request):
    from clients.models import Client as _Client
    from products.models import Product as _Product

    clients = _Client.objects.filter(is_active=True).order_by("name")
    products = _Product.objects.filter(is_active=True).select_related("category").order_by("name")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        client_id = request.POST.get("client_id", "").strip()
        task_date = request.POST.get("task_date", "").strip()
        note = request.POST.get("note", "").strip()

        errors = []
        if not title:
            errors.append("Le titre est requis.")
        if not client_id:
            errors.append("Le client est requis.")
        if not task_date:
            errors.append("La date est requise.")

        client = None
        if client_id:
            try:
                client = _Client.objects.get(pk=int(client_id), is_active=True)
            except (_Client.DoesNotExist, ValueError):
                errors.append("Client introuvable.")

        if errors:
            return render(request, "services/task_form.html", {
                "clients": clients, "products": products,
                "errors": errors, "post": request.POST,
            })

        task = Task.objects.create(
            title=title, client=client, task_date=task_date, note=note,
        )

        product_ids = request.POST.getlist("product_id")
        quantities  = request.POST.getlist("product_qty")
        for pid, qty_str in zip(product_ids, quantities):
            try:
                product = _Product.objects.get(pk=int(pid), is_active=True)
                qty = max(1, int(qty_str or 1))
                TaskProduct.objects.create(task=task, product=product, quantity=qty)
            except (_Product.DoesNotExist, ValueError):
                pass

        messages.success(request, f"Tâche « {task.title} » créée.")
        return redirect("services:task_detail", pk=task.pk)

    return render(request, "services/task_form.html", {
        "clients": clients, "products": products,
        "today": timezone.now().date().isoformat(),
    })


@login_required
def task_detail(request, pk):
    task = get_object_or_404(
        Task.objects.select_related("client").prefetch_related("task_products__product"),
        pk=pk,
    )
    return render(request, "services/task_detail.html", {"task": task})


@login_required
@require_POST
def task_complete(request, pk):
    """Terminer une tâche = créer la vente associée (si produits) + marquer terminée.
    Réouvrir une tâche déjà terminée = simple bascule sans action commerciale."""
    from sales.models import Sale, SaleItem

    task = get_object_or_404(
        Task.objects.select_related("client").prefetch_related("task_products__product"),
        pk=pk,
    )

    # ── Réouverture ──────────────────────────────────────────────────────────
    if task.is_completed:
        task.is_completed = False
        task.save(update_fields=["is_completed"])
        messages.success(request, f"Tâche « {task.title} » réouverte.")
        return redirect(request.POST.get("next", "services:task_list"))

    # ── Complétion → créer une vente ─────────────────────────────────────────
    task_products = list(task.task_products.select_related("product").all())

    if not task_products:
        # Pas de produits : on marque juste comme terminée
        task.is_completed = True
        task.save(update_fields=["is_completed"])
        messages.success(request, f"Tâche « {task.title} » terminée (aucun produit à facturer).")
        return redirect(request.POST.get("next", "services:task_list"))

    try:
        with transaction.atomic():
            from products.models import Product as _Product
            sale = Sale.objects.create(
                client=task.client,
                created_by=request.user,
                sale_date=_date.today(),  # date d'enregistrement, pas date planifiée
            )
            for tp in task_products:
                # Verrou pour éviter les conflits de stock concurrents
                product = _Product.objects.select_for_update().get(pk=tp.product_id)
                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=tp.quantity,
                    unit_price=product.selling_price,
                    purchase_price_snapshot=product.purchase_price,
                )
            sale.recompute_totals()
            sale.update_payment_status()
            task.is_completed = True
            task.save(update_fields=["is_completed"])
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("services:task_detail", pk=pk)

    nb = len(task_products)
    messages.success(
        request,
        f"Tâche « {task.title} » terminée — vente créée ({nb} produit{'s' if nb > 1 else ''}).",
    )
    return redirect("sales:detail", pk=sale.pk)


@login_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    title = task.title
    task.delete()
    messages.success(request, f"Tâche « {title} » supprimée.")
    return redirect("services:task_list")


@login_required
@require_POST
def task_to_sale(request, pk):
    """Convertit une tâche en vente : crée la vente + lignes produits, marque la tâche terminée."""
    from sales.models import Sale, SaleItem

    task = get_object_or_404(
        Task.objects.select_related("client").prefetch_related("task_products__product"),
        pk=pk,
    )

    try:
        with transaction.atomic():
            sale = Sale.objects.create(
                client=task.client,
                created_by=request.user,
                sale_date=task.task_date,
            )
            for tp in task.task_products.select_related("product").all():
                SaleItem.objects.create(
                    sale=sale,
                    product=tp.product,
                    quantity=tp.quantity,
                    unit_price=tp.product.selling_price,
                    purchase_price_snapshot=tp.product.purchase_price,
                )
            sale.recompute_totals()
            task.is_completed = True
            task.save(update_fields=["is_completed"])
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("services:task_detail", pk=pk)

    nb = task.task_products.count()
    msg = (
        f"Vente créée depuis la tâche « {task.title} »"
        + (f" ({nb} produit{'s' if nb > 1 else ''})." if nb else " (sans produit — ajoutez les articles manuellement).")
    )
    messages.success(request, msg)
    return redirect("sales:detail", pk=sale.pk)


# ── Assigner des prestations ──────────────────────────────────────────────────

@login_required
def service_assign(request):
    """
    Assigner des prestations à un client depuis le module Services.
    Crée une vente en arrière-plan avec les prestations sélectionnées.
    Même logique que sale_create mais sans la section Produits.
    """
    import json as _json
    from clients.models import Client
    from sales.models import Payment, Sale, SaleItem

    services = Service.objects.filter(is_active=True).order_by("name")
    services_data = [
        {"id": s.id, "name": s.name, "price": str(s.price)}
        for s in services
    ]

    if request.method == "POST":
        cart_raw = request.POST.get("cart_data", "")
        client_id = request.POST.get("client_id", "").strip()
        payment_amount_raw = request.POST.get("payment_amount", "").strip()
        payment_method = request.POST.get("payment_method", "cash")

        try:
            cart = _json.loads(cart_raw) if cart_raw else []
        except _json.JSONDecodeError:
            cart = []

        if not cart:
            return render(request, "services/assign.html", {
                "services_data": services_data,
                "error": "Aucune prestation sélectionnée.",
            })

        # Client obligatoire pour les prestations
        client = None
        if client_id:
            try:
                client = Client.objects.get(pk=int(client_id), is_active=True)
            except (Client.DoesNotExist, ValueError):
                client = None

        if not client:
            return render(request, "services/assign.html", {
                "services_data": services_data,
                "error": "Un client est requis pour assigner des prestations.",
            })

        try:
            with transaction.atomic():
                sale = Sale.objects.create(
                    client=client,
                    created_by=request.user,
                    sale_date=_date.today(),
                )

                for item in cart:
                    item_id = item.get("id")
                    qty = int(item.get("qty", 1))
                    unit_price_raw = item.get("unit_price", "0")
                    try:
                        unit_price = Decimal(str(unit_price_raw))
                    except (InvalidOperation, TypeError, ValueError):
                        unit_price = Decimal("0.00")

                    service_obj = Service.objects.get(pk=item_id)
                    tours_per_month_raw = item.get("tours_per_month")
                    tours_per_month = int(tours_per_month_raw) if tours_per_month_raw else None
                    start_tour_raw = item.get("start_tour")
                    start_tour = int(start_tour_raw) if start_tour_raw else 1
                    exec_qty_raw = item.get("exec_qty")
                    exec_qty = int(exec_qty_raw) if exec_qty_raw else qty

                    sale_item = SaleItem.objects.create(
                        sale=sale,
                        service=service_obj,
                        quantity=qty,
                        unit_price=unit_price,
                        purchase_price_snapshot=Decimal("0.00"),
                    )

                    # Premier passage
                    first_exec = ServiceExecution.objects.create(
                        client=client,
                        service=service_obj,
                        sale_item=sale_item,
                        execution_date=sale.sale_date,
                        next_due_date=sale.sale_date,
                        tours_per_month=tours_per_month,
                        start_tour=start_tour,
                    )

                    # Passages suivants
                    if exec_qty > 1 and tours_per_month:
                        interval = first_exec.interval_days() or 0
                        prev_date = sale.sale_date
                        for i in range(1, exec_qty):
                            raw_date = prev_date + timedelta(days=interval)
                            offset = (sale.sale_date.weekday() - raw_date.weekday()) % 7
                            child_date = raw_date + timedelta(days=offset)
                            prev_date = child_date
                            child_tour = ((start_tour - 1 + i) % tours_per_month) + 1
                            ServiceExecution.objects.create(
                                client=client,
                                service=service_obj,
                                tours_per_month=tours_per_month,
                                execution_date=child_date,
                                next_due_date=child_date,
                                parent_execution=first_exec,
                                start_tour=child_tour,
                            )

                sale.recompute_totals()

                # Paiement optionnel
                try:
                    payment_amount = Decimal(payment_amount_raw) if payment_amount_raw else Decimal("0.00")
                except (InvalidOperation, TypeError, ValueError):
                    payment_amount = Decimal("0.00")

                if payment_amount > Decimal("0.00"):
                    if payment_amount > sale.total_amount:
                        payment_amount = sale.total_amount
                    valid_methods = [m[0] for m in Payment.Method.choices]
                    if payment_method not in valid_methods:
                        payment_method = "cash"
                    Payment.objects.create(
                        sale=sale,
                        recorded_by=request.user,
                        amount=payment_amount,
                        payment_method=payment_method,
                        payment_date=_date.today(),
                    )

        except Exception as e:
            return render(request, "services/assign.html", {
                "services_data": services_data,
                "error": f"Erreur : {e}",
            })

        nb = len(cart)
        messages.success(
            request,
            f"Vente créée — {nb} prestation{'s' if nb > 1 else ''} assignée{'s' if nb > 1 else ''} à {client.name}.",
        )
        return redirect("sales:detail", pk=sale.pk)

    return render(request, "services/assign.html", {
        "services_data": services_data,
    })
