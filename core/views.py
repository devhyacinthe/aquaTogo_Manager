import json as _json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Sum, Value, When
from django.db.models.functions import Coalesce, TruncMonth, TruncDay
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .forms import PasswordUpdateForm, ProfileForm
from .models import UserProfile


class AquaLoginView(LoginView):
    template_name = "auth/login.html"
    redirect_authenticated_user = True

    def form_invalid(self, form):
        messages.error(self.request, "Identifiant ou mot de passe incorrect.")
        return super().form_invalid(form)


class AquaLogoutView(LogoutView):
    next_page = "core:login"


@login_required
def dashboard(request):
    from products.models import Product
    from sales.models import Payment, Sale, SaleItem
    from services.models import ServiceExecution

    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    _zero = Value(Decimal("0.00"))
    _df = DecimalField(max_digits=14, decimal_places=2)

    # CA = argent encaissé (payment_date), profit = proportion du bénéfice de la vente
    def payment_stats(start, end):
        qs = Payment.objects.filter(payment_date__gte=start, payment_date__lte=end).annotate(
            prop_profit=Case(
                When(
                    sale__total_amount__gt=0,
                    then=ExpressionWrapper(
                        F("amount") * F("sale__total_profit") / F("sale__total_amount"),
                        output_field=_df,
                    ),
                ),
                default=_zero,
                output_field=_df,
            )
        )
        agg = qs.aggregate(
            ca=Coalesce(Sum("amount"), _zero, output_field=_df),
            profit=Coalesce(Sum("prop_profit"), _zero, output_field=_df),
        )
        return {
            "ca": agg["ca"],
            "profit": agg["profit"],
            "count": qs.values("sale").distinct().count(),
        }

    stats_day   = payment_stats(today, today)
    stats_week  = payment_stats(start_of_week, today)
    stats_month = payment_stats(start_of_month, today)

    top_products = (
        SaleItem.objects.filter(product__isnull=False, sale__sale_date__gte=start_of_month)
        .values("product__name", "product__category__name")
        .annotate(total_qty=Sum("quantity"), total_revenue=Sum("line_total"))
        .order_by("-total_qty")[:5]
    )

    top_services = (
        SaleItem.objects.filter(service__isnull=False, sale__sale_date__gte=start_of_month)
        .values("service__name")
        .annotate(total_qty=Sum("quantity"), total_revenue=Sum("line_total"))
        .order_by("-total_qty")[:5]
    )

    low_stock = Product.objects.filter(
        is_active=True,
        stock_quantity__lte=F("low_stock_threshold"),
    ).order_by("stock_quantity")[:8]

    upcoming_executions = (
        ServiceExecution.objects.filter(is_completed=False, next_due_date__isnull=False)
        .select_related("client", "service")
        .order_by("next_due_date")[:6]
    )

    unpaid_count = Sale.objects.filter(payment_status__in=["unpaid", "partial"]).count()

    tomorrow = today + timedelta(days=1)
    due_tomorrow = (
        ServiceExecution.objects.filter(
            is_completed=False, next_due_date=tomorrow
        )
        .select_related("client", "service")
        .order_by("client__name")
    )

    from accounting.models import Expense
    # Exclure les achats de stock : déjà comptés dans le COGS (purchase_price_snapshot)
    total_expenses_month = (
        Expense.objects.filter(expense_date__gte=start_of_month)
        .exclude(category=Expense.Category.STOCK)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    net_profit_month = (stats_month["profit"] or Decimal("0.00")) - total_expenses_month

    # ── Graphe — évolution sur 30 jours (par date d'encaissement) ────────────
    chart_start = today - timedelta(days=29)
    daily_rows = (
        Payment.objects
        .filter(payment_date__gte=chart_start, payment_date__lte=today)
        .annotate(
            prop_profit=Case(
                When(
                    sale__total_amount__gt=0,
                    then=ExpressionWrapper(
                        F("amount") * F("sale__total_profit") / F("sale__total_amount"),
                        output_field=_df,
                    ),
                ),
                default=_zero,
                output_field=_df,
            )
        )
        .values("payment_date")
        .annotate(ca=Sum("amount"), profit=Sum("prop_profit"))
        .order_by("payment_date")
    )
    date_map = {row["payment_date"]: row for row in daily_rows}

    expense_rows = (
        Expense.objects
        .filter(expense_date__gte=chart_start, expense_date__lte=today)
        .values("expense_date")
        .annotate(total=Sum("amount"))
        .order_by("expense_date")
    )
    expense_date_map = {row["expense_date"]: row for row in expense_rows}

    chart_labels, chart_ca, chart_profit, chart_expenses = [], [], [], []
    for i in range(30):
        d = chart_start + timedelta(days=i)
        chart_labels.append(d.strftime("%d/%m"))
        row = date_map.get(d)
        chart_ca.append(float(row["ca"]) if row else 0)
        chart_profit.append(float(row["profit"]) if row else 0)
        exp_row = expense_date_map.get(d)
        chart_expenses.append(float(exp_row["total"]) if exp_row else 0)

    return render(request, "core/dashboard.html", {
        "stats_day":   stats_day,
        "stats_week":  stats_week,
        "stats_month": stats_month,
        "total_expenses_month": total_expenses_month,
        "net_profit_month": net_profit_month,
        "top_products": top_products,
        "top_services": top_services,
        "low_stock": low_stock,
        "upcoming_executions": upcoming_executions,
        "unpaid_count": unpaid_count,
        "today": today,
        "due_tomorrow": due_tomorrow,
        "chart_labels":   _json.dumps(chart_labels),
        "chart_ca":       _json.dumps(chart_ca),
        "chart_profit":   _json.dumps(chart_profit),
        "chart_expenses": _json.dumps(chart_expenses),
    })


@login_required
def profile(request):
    user = request.user
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)

    profile_form = ProfileForm(instance=user, profile=profile_obj)
    password_form = PasswordUpdateForm(user=user)

    active_tab = "profil"

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "update_profile":
            profile_form = ProfileForm(request.POST, instance=user, profile=profile_obj)
            if profile_form.is_valid():
                profile_form.save()
                profile_obj.phone = profile_form.cleaned_data.get("phone", "")
                profile_obj.save()
                messages.success(request, "Profil mis à jour avec succès.")
                return redirect("core:profile")
            active_tab = "profil"

        elif action == "update_password":
            password_form = PasswordUpdateForm(user=user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Mot de passe modifié avec succès.")
                return redirect("core:profile")
            active_tab = "securite"

    return render(request, "auth/profile.html", {
        "profile_form": profile_form,
        "password_form": password_form,
        "active_tab": active_tab,
    })


@login_required
@require_GET
def dashboard_chart_data(request):
    from sales.models import Payment
    from accounting.models import Expense

    period = request.GET.get("period", "month")
    today = timezone.now().date()

    _zero = Value(Decimal("0.00"))
    _df = DecimalField(max_digits=14, decimal_places=2)

    if period == "week":
        chart_start = today - timedelta(days=6)
        trunc_fn = TruncDay
        date_fmt = "%d/%m"
        days_range = [(chart_start + timedelta(days=i)) for i in range(7)]
        key_fn = lambda d: d  # noqa: E731
    elif period == "year":
        from dateutil.relativedelta import relativedelta
        chart_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        chart_start = chart_start - timedelta(days=11 * 30)
        chart_start = chart_start.replace(day=1)
        trunc_fn = TruncMonth
        date_fmt = "%b %Y"
        days_range = [chart_start + timedelta(days=i * 30) for i in range(12)]
        days_range = [d.replace(day=1) for d in days_range]
        key_fn = lambda d: d.replace(day=1)  # noqa: E731
    elif period == "5years":
        from dateutil.relativedelta import relativedelta
        chart_start = today.replace(day=1, month=1) - timedelta(days=4 * 365)
        chart_start = chart_start.replace(day=1)
        trunc_fn = TruncMonth
        date_fmt = "%b %Y"
        days_range = [chart_start + timedelta(days=i * 30) for i in range(60)]
        days_range = [d.replace(day=1) for d in days_range]
        # deduplicate while preserving order
        seen = set()
        days_range = [d for d in days_range if not (d in seen or seen.add(d))]
        key_fn = lambda d: d.replace(day=1)  # noqa: E731
    else:  # month (default)
        chart_start = today - timedelta(days=29)
        trunc_fn = TruncDay
        date_fmt = "%d/%m"
        days_range = [(chart_start + timedelta(days=i)) for i in range(30)]
        key_fn = lambda d: d  # noqa: E731

    # Payments
    pay_rows = (
        Payment.objects
        .filter(payment_date__gte=chart_start, payment_date__lte=today)
        .annotate(
            prop_profit=Case(
                When(
                    sale__total_amount__gt=0,
                    then=ExpressionWrapper(
                        F("amount") * F("sale__total_profit") / F("sale__total_amount"),
                        output_field=_df,
                    ),
                ),
                default=_zero,
                output_field=_df,
            ),
            period=trunc_fn("payment_date"),
        )
        .values("period")
        .annotate(ca=Sum("amount"), profit=Sum("prop_profit"))
        .order_by("period")
    )
    pay_map = {row["period"].date() if hasattr(row["period"], "date") else row["period"]: row for row in pay_rows}

    # Expenses
    exp_rows = (
        Expense.objects
        .filter(expense_date__gte=chart_start, expense_date__lte=today)
        .annotate(period=trunc_fn("expense_date"))
        .values("period")
        .annotate(total=Sum("amount"))
        .order_by("period")
    )
    exp_map = {row["period"].date() if hasattr(row["period"], "date") else row["period"]: row for row in exp_rows}

    labels, ca_data, profit_data, expense_data = [], [], [], []
    for d in days_range:
        k = key_fn(d)
        labels.append(d.strftime(date_fmt))
        pay = pay_map.get(k)
        ca_data.append(float(pay["ca"]) if pay else 0)
        profit_data.append(float(pay["profit"]) if pay else 0)
        exp = exp_map.get(k)
        expense_data.append(float(exp["total"]) if exp else 0)

    return JsonResponse({
        "labels": labels,
        "ca": ca_data,
        "profit": profit_data,
        "expenses": expense_data,
    })
