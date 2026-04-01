from datetime import timedelta
from decimal import Decimal

from django.utils import timezone


def generate_daily_report() -> str:
    """
    Construit le message HTML du résumé quotidien.
    - CA  = encaissements du jour (Payment.payment_date = today)
    - Bénéfice = proportion du profit de chaque vente encaissée
    - Prestations J+1 = ServiceExecution dues demain
    """
    from accounting.models import Expense
    from sales.models import Payment, SaleItem
    from services.models import ServiceExecution

    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)

    # ── Encaissements du jour ─────────────────────────────────────────────────
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

    # ── Dépenses du jour ──────────────────────────────────────────────────────
    from django.db.models import Sum
    total_expenses = (
        Expense.objects.filter(expense_date=today)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    net_profit = total_profit - total_expenses

    # ── Top produit du jour ───────────────────────────────────────────────────
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

    # ── Prestations pour demain ───────────────────────────────────────────────
    services_tomorrow = list(
        ServiceExecution.objects.filter(
            next_due_date=tomorrow,
            is_completed=False,
        ).select_related("client", "service")
    )

    # ── Mise en forme HTML (Telegram) ─────────────────────────────────────────
    date_fr = today.strftime("%d/%m/%Y")
    lines = [
        f"📊 <b>Résumé AquaTogo — {date_fr}</b>",
        "",
        f"🧾 Ventes encaissées : <b>{nb_ventes}</b>",
        f"💰 Chiffre d'affaires : <b>{total_ca:,.0f} FCFA</b>",
        f"📈 Bénéfice brut : <b>{total_profit:,.0f} FCFA</b>",
        f"🏦 Dépenses du jour : <b>{total_expenses:,.0f} FCFA</b>",
        f"{'✅' if net_profit >= 0 else '🔴'} Résultat net : <b>{net_profit:,.0f} FCFA</b>",
    ]

    if top:
        lines += ["", f"🐟 Meilleure vente : <b>{top['product__name']}</b> (× {top['qty']})"]

    lines.append("")
    if services_tomorrow:
        lines.append(f"🔧 <b>Prestations demain ({len(services_tomorrow)}) :</b>")
        for s in services_tomorrow:
            lines.append(f"  • {s.service.name} — {s.client.name}")
    else:
        lines.append("🔧 Aucune prestation prévue demain.")

    return "\n".join(lines)
