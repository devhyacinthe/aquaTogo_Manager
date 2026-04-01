from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ExpenseForm
from .models import Expense


def _period_range(periode):
    today = date.today()
    if periode == "today":
        return today, today, "Aujourd'hui"
    if periode == "week":
        start = today - timedelta(days=today.weekday())
        return start, today, "Cette semaine"
    if periode == "all":
        return None, None, "Tout"
    # default: month
    start = today.replace(day=1)
    return start, today, "Ce mois"


@login_required
def expense_list(request):
    periode = request.GET.get("periode", "month")
    category_filter = request.GET.get("category", "")

    start, end, periode_label = _period_range(periode)

    qs = Expense.objects.all()
    if start:
        qs = qs.filter(expense_date__gte=start, expense_date__lte=end)
    if category_filter:
        qs = qs.filter(category=category_filter)

    total_expenses = qs.aggregate(
        total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2))
    )["total"]

    context = {
        "expenses": qs,
        "total_expenses": total_expenses,
        "expense_count": qs.count(),
        "periode": periode,
        "periode_label": periode_label,
        "category_filter": category_filter,
        "categories": Expense.Category.choices,
    }
    return render(request, "accounting/expense_list.html", context)


@login_required
def expense_create(request):
    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save()
            messages.success(request, f"Dépense « {expense.label} » enregistrée.")
            return redirect("accounting:list")
    else:
        form = ExpenseForm(initial={"expense_date": date.today()})

    context = {
        "form": form,
        "title": "Nouvelle dépense",
        "submit_label": "Enregistrer la dépense",
        "is_edit": False,
    }
    return render(request, "accounting/expense_form.html", context)


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)

    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, f"Dépense « {expense.label} » mise à jour.")
            return redirect("accounting:list")
    else:
        form = ExpenseForm(instance=expense)

    context = {
        "form": form,
        "expense": expense,
        "title": f"Modifier « {expense.label} »",
        "submit_label": "Mettre à jour",
        "is_edit": True,
    }
    return render(request, "accounting/expense_form.html", context)


@login_required
def expense_delete(request, pk):
    if request.method != "POST":
        return redirect("accounting:list")
    expense = get_object_or_404(Expense, pk=pk)
    label = expense.label
    expense.delete()
    messages.success(request, f"Dépense « {label} » supprimée.")
    return redirect("accounting:list")


@login_required
def expense_export_excel(request):
    from io import BytesIO
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse

    periode = request.GET.get("periode", "month")
    category_filter = request.GET.get("category", "")
    start, end, periode_label = _period_range(periode)

    qs = Expense.objects.all()
    if start:
        qs = qs.filter(expense_date__gte=start, expense_date__lte=end)
    if category_filter:
        qs = qs.filter(category=category_filter)
    qs = qs.order_by("expense_date", "id")

    total = qs.aggregate(
        total=Coalesce(Sum("amount"), Value(Decimal("0.00")),
                       output_field=DecimalField(max_digits=14, decimal_places=2))
    )["total"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dépenses"

    BRAND_BLUE = "1E40AF"
    LIGHT_BLUE = "DBEAFE"
    GRAY_ROW   = "F9FAFB"
    WHITE      = "FFFFFF"

    thin = Side(style="thin", color="E5E7EB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Titre
    ws.merge_cells("A1:E1")
    title_cell = ws["A1"]
    title_cell.value = f"Dépenses — {periode_label}"
    title_cell.font = Font(name="Calibri", bold=True, size=14, color=WHITE)
    title_cell.fill = PatternFill("solid", fgColor=BRAND_BLUE)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    # En-têtes
    headers = ["Date", "Libellé", "Catégorie", "Note", "Montant (FCFA)"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.font = Font(name="Calibri", bold=True, size=11, color=WHITE)
        cell.fill = PatternFill("solid", fgColor=BRAND_BLUE)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border
    ws.row_dimensions[2].height = 22

    category_labels = dict(Expense.Category.choices)

    for i, expense in enumerate(qs):
        row = i + 3
        fill = PatternFill("solid", fgColor=GRAY_ROW if i % 2 == 0 else WHITE)

        cells = [
            (1, expense.expense_date.strftime("%d/%m/%Y")),
            (2, expense.label),
            (3, category_labels.get(expense.category, expense.category)),
            (4, expense.note or ""),
            (5, float(expense.amount)),
        ]
        for col, val in cells:
            c = ws.cell(row=row, column=col, value=val)
            c.fill = fill
            c.font = Font(name="Calibri", size=10)
            c.border = border
            if col == 5:
                c.number_format = '#,##0'
                c.alignment = Alignment(horizontal="right")

    # Ligne total
    total_row = qs.count() + 3
    ws.merge_cells(f"A{total_row}:D{total_row}")
    label_cell = ws.cell(row=total_row, column=1, value="TOTAL")
    label_cell.font = Font(name="Calibri", bold=True, size=11, color=WHITE)
    label_cell.fill = PatternFill("solid", fgColor=BRAND_BLUE)
    label_cell.alignment = Alignment(horizontal="right", vertical="center")
    label_cell.border = border

    total_cell = ws.cell(row=total_row, column=5, value=float(total))
    total_cell.font = Font(name="Calibri", bold=True, size=11, color=WHITE)
    total_cell.fill = PatternFill("solid", fgColor=BRAND_BLUE)
    total_cell.number_format = '#,##0'
    total_cell.alignment = Alignment(horizontal="right")
    total_cell.border = border
    ws.row_dimensions[total_row].height = 22

    # Largeurs colonnes
    col_widths = [14, 40, 22, 35, 18]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"depenses_{periode}.xlsx"
    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def accounting_report(request):
    from sales.models import Payment

    periode = request.GET.get("periode", "month")
    start, end, periode_label = _period_range(periode)

    _zero = Value(Decimal("0.00"))
    _df = DecimalField(max_digits=14, decimal_places=2)

    # CA et bénéfice basés sur les encaissements (payment_date)
    pay_qs = Payment.objects.all()
    if start:
        pay_qs = pay_qs.filter(payment_date__gte=start, payment_date__lte=end)

    # On calcule product_revenue et service_revenue par vente via Python
    # (plus simple et fiable que de sous-annoter depuis Payment)
    pay_list = list(pay_qs.select_related("sale").prefetch_related("sale__items"))

    total_ca    = Decimal("0.00")
    gross_profit = Decimal("0.00")
    rev_products = Decimal("0.00")
    rev_services = Decimal("0.00")
    sale_ids = set()

    for payment in pay_list:
        sale = payment.sale
        total_ca += payment.amount
        sale_ids.add(sale.id)
        if sale.total_amount > 0:
            prop = payment.amount / sale.total_amount
            gross_profit += sale.total_profit * prop
            prod_total = sum(
                item.line_total for item in sale.items.all() if item.product_id
            )
            svc_total = sum(
                item.line_total for item in sale.items.all() if item.service_id
            )
            rev_products += prop * prod_total
            rev_services += prop * svc_total

    sale_count = len(sale_ids)
    pct_products = int(rev_products / total_ca * 100) if total_ca > 0 else 0
    pct_services = int(rev_services / total_ca * 100) if total_ca > 0 else 0

    expense_qs = Expense.objects.all()
    if start:
        expense_qs = expense_qs.filter(expense_date__gte=start, expense_date__lte=end)

    total_expenses = expense_qs.aggregate(
        total=Coalesce(Sum("amount"), _zero, output_field=_df)
    )["total"]

    expenses_by_category = list(
        expense_qs.values("category")
        .annotate(subtotal=Sum("amount"))
        .order_by("-subtotal")
    )

    category_labels = dict(Expense.Category.choices)
    for row in expenses_by_category:
        row["cat_label"] = category_labels.get(row["category"], row["category"])
        row["pct"] = (row["subtotal"] / total_expenses * 100) if total_expenses > 0 else Decimal("0")

    net_profit = gross_profit - total_expenses
    cogs = total_ca - gross_profit
    profit_margin = (net_profit / total_ca * 100) if total_ca > 0 else Decimal("0")

    # Capital actuel = cumul tous les temps (encaissements proportionnels - dépenses)
    from sales.models import Sale
    all_time_profit = Sale.objects.aggregate(
        total=Coalesce(Sum("total_profit"), _zero, output_field=_df)
    )["total"]
    all_time_expenses = Expense.objects.aggregate(
        total=Coalesce(Sum("amount"), _zero, output_field=_df)
    )["total"]
    capital_actuel = all_time_profit - all_time_expenses

    context = {
        "total_ca": total_ca,
        "gross_profit": gross_profit,
        "cogs": cogs,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "is_profitable": net_profit >= 0,
        "expenses_by_category": expenses_by_category,
        "sale_count": sale_count,
        "expense_count": expense_qs.count(),
        "periode": periode,
        "periode_label": periode_label,
        "rev_products": rev_products,
        "rev_services": rev_services,
        "pct_products": pct_products,
        "pct_services": pct_services,
        "capital_actuel": capital_actuel,
        "capital_positif": capital_actuel >= 0,
    }
    return render(request, "accounting/report.html", context)
