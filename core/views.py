import json as _json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Sum, Value, When
from django.db.models.functions import Coalesce, TruncMonth, TruncDay
from django.http import HttpResponse, JsonResponse
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

    def get_success_url(self):
        from django.urls import reverse
        profile = getattr(self.request.user, "profile", None)
        if profile and profile.is_employe:
            return reverse("services:execution_list")
        return super().get_success_url()


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
        "tomorrow": tomorrow,
        "due_tomorrow": due_tomorrow,
        "chart_labels":   _json.dumps(chart_labels),
        "chart_ca":       _json.dumps(chart_ca),
        "chart_profit":   _json.dumps(chart_profit),
        "chart_expenses": _json.dumps(chart_expenses),
    })


def _logo_path():
    from django.contrib.staticfiles.finders import find
    return find("img/logo.png") or ""


def _fmt(n):
    return f"{int(n):,}".replace(",", " ")


def _build_pdf(buffer, title_text, subtitle_text, col_headers, rows, col_widths,
               extra_story=None):
    """Génère un PDF avec logo, en-tête, éléments optionnels puis tableau."""
    import os
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable, Image, Paragraph, SimpleDocTemplate,
        Spacer, Table, TableStyle,
    )

    PAGE = landscape(A4)
    W = PAGE[0]
    BRAND     = colors.HexColor("#2563eb")
    DARK      = colors.HexColor("#1e3a5f")
    GRAY      = colors.HexColor("#6b7280")
    ROW_ALT   = colors.HexColor("#f0f4ff")

    title_st = ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=15,
                               textColor=BRAND, leading=18, alignment=TA_LEFT)
    sub_st   = ParagraphStyle("S", fontName="Helvetica", fontSize=8.5,
                               textColor=GRAY, spaceAfter=2, alignment=TA_LEFT)

    doc = SimpleDocTemplate(
        buffer, pagesize=PAGE,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )

    # ── En-tête : logo + titre ────────────────────────────────────────────────
    logo = _logo_path()
    logo_cell = Image(logo, width=1.6*cm, height=1.6*cm) if logo and os.path.exists(logo) else ""

    title_block = [Paragraph(title_text, title_st), Paragraph(subtitle_text, sub_st)]
    hdr_table = Table(
        [[logo_cell, title_block]],
        colWidths=[2*cm, W - 1.5*cm - 1.5*cm - 2*cm],
    )
    hdr_table.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("LEFTPADDING",  (1, 0), (1, 0), 0),
    ]))

    # ── Tableau principal ─────────────────────────────────────────────────────
    table_data = [col_headers] + (rows if rows else [["—"] * len(col_headers)])
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    n = len(table_data)
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  9),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, 0),  7),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  7),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8.5),
        ("TOPPADDING",    (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("ALIGN",         (0, 1), (-1, -1), "LEFT"),
        *[("BACKGROUND",  (0, i), (-1, i),  ROW_ALT) for i in range(2, n, 2)],
        ("GRID",          (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
        ("LINEABOVE",     (0, 1), (-1, 1),  1, BRAND),
    ]))

    # ── Pied de page ──────────────────────────────────────────────────────────
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRAY)
        canvas.drawString(1.5*cm, 0.7*cm, "AquaTogo Manager")
        canvas.drawRightString(W - 1.5*cm, 0.7*cm, f"Page {doc.page}")
        canvas.restoreState()

    story = [hdr_table, HRFlowable(width="100%", thickness=1, color=BRAND, spaceAfter=10)]
    if extra_story:
        story += extra_story
    story.append(table)

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


@login_required
def download_prestations_demain(request):
    import io
    from services.models import ServiceExecution

    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)

    executions = (
        ServiceExecution.objects
        .filter(is_completed=False, next_due_date=tomorrow)
        .select_related("client", "service")
        .order_by("scheduled_time", "client__name")
    )

    rows = []
    for ex in executions:
        rows.append([
            ex.client.name if ex.client else "—",
            ex.client.phone if ex.client and ex.client.phone else "—",
            ex.service.name,
            f"Tour {ex.start_tour or 1}" if ex.tours_per_month else "Ponctuel",
            ex.scheduled_time.strftime("%H:%M") if ex.scheduled_time else "—",
        ])

    from reportlab.lib.units import cm
    buf = io.BytesIO()
    _build_pdf(
        buf,
        title_text=f"Prestations du {tomorrow.strftime('%d/%m/%Y')}",
        subtitle_text=f"Planning des interventions  —  {len(rows)} passage{'s' if len(rows) != 1 else ''}",
        col_headers=["Client", "Telephone", "Prestation", "Tour", "Heure prevue"],
        rows=rows,
        col_widths=[6*cm, 4*cm, 7*cm, 3*cm, 3.5*cm],
    )
    buf.seek(0)
    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="prestations_{tomorrow.strftime("%Y-%m-%d")}.pdf"'
    )
    return response


@login_required
def download_ventes_aujourd_hui(request):
    import io
    from decimal import Decimal as D
    from sales.models import Payment, Sale, SaleItem
    from accounting.models import Expense
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable

    today = timezone.now().date()
    _zero = Value(D("0.00"))
    _df   = DecimalField(max_digits=14, decimal_places=2)

    # ── Stats du jour ─────────────────────────────────────────────────────────
    pay_agg = (
        Payment.objects.filter(payment_date=today)
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
        .aggregate(
            ca=Coalesce(Sum("amount"), _zero, output_field=_df),
            profit=Coalesce(Sum("prop_profit"), _zero, output_field=_df),
        )
    )
    nb_ventes = Payment.objects.filter(payment_date=today).values("sale").distinct().count()
    ca       = pay_agg["ca"]      or D("0")
    profit   = pay_agg["profit"]  or D("0")
    depenses = (
        Expense.objects.filter(expense_date=today)
        .aggregate(t=Coalesce(Sum("amount"), _zero, output_field=_df))["t"]
        or D("0")
    )
    net = profit - depenses

    # ── Lignes du tableau ─────────────────────────────────────────────────────
    items = (
        SaleItem.objects
        .filter(sale__sale_date=today, sale__status="active", product__isnull=False)
        .select_related("product", "sale__client")
        .order_by("sale__created_at", "product__name")
    )
    rows = []
    for item in items:
        rows.append([
            item.product.name,
            str(item.quantity),
            _fmt(item.unit_price),
            _fmt(item.line_total),
            item.sale.client.name if item.sale.client else "Anonyme",
            item.sale.created_at.astimezone().strftime("%H:%M"),
        ])
    total_ligne = sum(item.line_total for item in items)
    if rows:
        rows.append(["", "", "TOTAL", _fmt(total_ligne), "", ""])

    # ── Bloc rapport (extra_story) ────────────────────────────────────────────
    BRAND  = colors.HexColor("#2563eb")
    DARK   = colors.HexColor("#1e3a5f")
    GREEN  = colors.HexColor("#16a34a")
    RED    = colors.HexColor("#dc2626")
    BGBOX  = colors.HexColor("#eff6ff")
    BORDER = colors.HexColor("#bfdbfe")

    lbl_st = ParagraphStyle("L", fontName="Helvetica-Bold", fontSize=9,
                             textColor=DARK, alignment=TA_LEFT)
    val_st = ParagraphStyle("V", fontName="Helvetica-Bold", fontSize=9,
                             textColor=BRAND, alignment=TA_RIGHT)
    net_col = GREEN if net >= 0 else RED
    net_st  = ParagraphStyle("N", fontName="Helvetica-Bold", fontSize=9,
                              textColor=net_col, alignment=TA_RIGHT)

    rapport_data = [
        [Paragraph("Rapport des ventes", ParagraphStyle(
            "RT", fontName="Helvetica-Bold", fontSize=11, textColor=DARK)),
         Paragraph(today.strftime("%d/%m/%Y"), ParagraphStyle(
            "RD", fontName="Helvetica", fontSize=10, textColor=BRAND, alignment=TA_RIGHT))],
    ]

    stats = [
        ("Ventes encaissees",  f"{nb_ventes} vente{'s' if nb_ventes != 1 else ''}"),
        ("Chiffre d'affaires", f"{_fmt(ca)} FCFA"),
        ("Benefice brut",      f"{_fmt(profit)} FCFA"),
        ("Depenses du jour",   f"{_fmt(depenses)} FCFA"),
    ]
    rapport_data += [[Paragraph(l, lbl_st), Paragraph(v, val_st)] for l, v in stats]
    rapport_data += [[
        Paragraph("Resultat net", ParagraphStyle("NL", fontName="Helvetica-Bold",
                                                  fontSize=9, textColor=net_col)),
        Paragraph(f"{'+ ' if net >= 0 else ''}{_fmt(net)} FCFA", net_st),
    ]]

    from reportlab.lib.pagesizes import A4, landscape
    W = landscape(A4)[0]
    box_w = (W - 3*cm) * 0.45

    rapport_table = Table(rapport_data, colWidths=[box_w * 0.55, box_w * 0.45])
    rapport_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BGBOX),
        ("LINEABOVE",     (0, 0), (-1, 0),  2, BRAND),
        ("LINEBELOW",     (0, -1),(-1, -1), 1.5, net_col),
        ("GRID",          (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("SPAN",          (0, 0), (-1, 0)),
        ("ALIGN",         (0, 0), (-1, 0), "LEFT"),
        ("FONTNAME",      (0, -1),(-1, -1), "Helvetica-Bold"),
    ]))

    extra = [rapport_table, Spacer(1, 0.5*cm)]

    buf = io.BytesIO()
    _build_pdf(
        buf,
        title_text=f"Ventes du {today.strftime('%d/%m/%Y')}",
        subtitle_text=f"Articles vendus aujourd'hui  —  {len(rows) - (1 if rows else 0)} ligne{'s' if len(rows) > 2 else ''}",
        col_headers=["Produit", "Qte", "Prix unitaire (FCFA)", "Total (FCFA)", "Client", "Heure"],
        rows=rows,
        col_widths=[6*cm, 2*cm, 4.5*cm, 4.5*cm, 5*cm, 2.5*cm],
        extra_story=extra,
    )
    buf.seek(0)
    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="ventes_{today.strftime("%Y-%m-%d")}.pdf"'
    )
    return response


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
        chart_start = today.replace(day=1) - relativedelta(months=11)
        trunc_fn = TruncMonth
        date_fmt = "%b %Y"
        days_range = [chart_start + relativedelta(months=i) for i in range(12)]
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
