import json as _json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import F, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

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
    from sales.models import Sale, SaleItem
    from services.models import ServiceExecution

    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    def sales_stats(qs):
        agg = qs.aggregate(ca=Sum("total_amount"), profit=Sum("total_profit"))
        return {
            "ca": agg["ca"] or 0,
            "profit": agg["profit"] or 0,
            "count": qs.count(),
        }

    stats_day   = sales_stats(Sale.objects.filter(sale_date=today))
    stats_week  = sales_stats(Sale.objects.filter(sale_date__gte=start_of_week))
    stats_month = sales_stats(Sale.objects.filter(sale_date__gte=start_of_month))

    top_products = (
        SaleItem.objects.filter(product__isnull=False, sale__sale_date__gte=start_of_month)
        .values("product__name", "product__category")
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

    # ── Graphe — évolution sur 30 jours ──────────────────────────────────────
    chart_start = today - timedelta(days=29)
    daily_rows = (
        Sale.objects
        .filter(sale_date__gte=chart_start, sale_date__lte=today)
        .values("sale_date")
        .annotate(ca=Sum("total_amount"), profit=Sum("total_profit"))
        .order_by("sale_date")
    )
    date_map = {row["sale_date"]: row for row in daily_rows}

    chart_labels, chart_ca, chart_profit = [], [], []
    for i in range(30):
        d = chart_start + timedelta(days=i)
        chart_labels.append(d.strftime("%d/%m"))
        row = date_map.get(d)
        chart_ca.append(float(row["ca"]) if row else 0)
        chart_profit.append(float(row["profit"]) if row else 0)

    return render(request, "core/dashboard.html", {
        "stats_day":   stats_day,
        "stats_week":  stats_week,
        "stats_month": stats_month,
        "top_products": top_products,
        "top_services": top_services,
        "low_stock": low_stock,
        "upcoming_executions": upcoming_executions,
        "unpaid_count": unpaid_count,
        "today": today,
        "chart_labels":  _json.dumps(chart_labels),
        "chart_ca":      _json.dumps(chart_ca),
        "chart_profit":  _json.dumps(chart_profit),
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
