from datetime import timedelta
from decimal import Decimal

from django.utils import timezone


def generate_sales_report() -> str:
    """Résumé des ventes encaissées aujourd'hui."""
    from django.db.models import Sum

    from accounting.models import Expense
    from sales.models import Payment, SaleItem

    today = timezone.now().date()

    payments_today = list(
        Payment.objects.filter(payment_date=today).select_related("sale")
    )

    total_ca = Decimal("0.00")
    total_profit = Decimal("0.00")
    sale_ids: set = set()

    for p in payments_today:
        total_ca += p.amount
        sale_ids.add(p.sale_id)
        if p.sale.total_amount > 0:
            total_profit += p.sale.total_profit * (p.amount / p.sale.total_amount)

    nb_ventes = len(sale_ids)

    total_expenses = (
        Expense.objects.filter(expense_date=today)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    net_profit = total_profit - total_expenses

    top = (
        SaleItem.objects.filter(
            product__isnull=False,
            sale__id__in=sale_ids,
        )
        .values("product__name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")
        .first()
    )

    date_fr = today.strftime("%d/%m/%Y")
    lines = [
        f"📊 <b>Rapport des ventes — {date_fr}</b>",
        "",
        f"🧾 Ventes encaissées : <b>{nb_ventes}</b>",
        f"💰 Chiffre d'affaires : <b>{total_ca:,.0f} FCFA</b>",
        f"📈 Bénéfice brut : <b>{total_profit:,.0f} FCFA</b>",
        f"🏦 Dépenses du jour : <b>{total_expenses:,.0f} FCFA</b>",
        f"{'✅' if net_profit >= 0 else '🔴'} Résultat net : <b>{net_profit:,.0f} FCFA</b>",
    ]

    if top:
        lines += ["", f"🐟 Meilleure vente : <b>{top['product__name']}</b> (× {top['qty']})"]

    return "\n".join(lines)


def generate_services_report() -> str:
    """Rappel des prestations prévues pour demain."""
    from services.models import ServiceExecution

    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)

    services_tomorrow = list(
        ServiceExecution.objects.filter(
            next_due_date=tomorrow,
            is_completed=False,
        ).select_related("client", "service")
    )

    tomorrow_fr = tomorrow.strftime("%d/%m/%Y")
    lines = [f"🔧 <b>Prestations du {tomorrow_fr}</b>", ""]

    if services_tomorrow:
        for s in services_tomorrow:
            lines.append(f"  • {s.service.name} — {s.client.name}")
    else:
        lines.append("Aucune prestation prévue.")

    return "\n".join(lines)


def generate_daily_report() -> str:
    """Rapport complet (ventes + prestations) en un seul message."""
    return generate_sales_report() + "\n\n" + generate_services_report()
