from datetime import timedelta

from django.db.models import F, Min
from django.utils import timezone


def get_overdue_clients(days: int = 30) -> list[dict]:
    """
    Retourne les clients ayant au moins une vente impayée ou partielle
    dont la date de vente dépasse `days` jours.
    Inclut le solde impayé et le nombre de jours de retard.
    """
    from clients.models import Client
    from sales.models import Sale

    cutoff = timezone.now().date() - timedelta(days=days)

    # Ventes impayées ou partielles plus vieilles que `days` jours, avec un client
    overdue_sales = (
        Sale.objects.filter(
            payment_status__in=["unpaid", "partial"],
            sale_date__lte=cutoff,
            client__isnull=False,
        )
        .values("client")
        .annotate(oldest_sale=Min("sale_date"))
    )

    client_ids = {row["client"]: row["oldest_sale"] for row in overdue_sales}
    if not client_ids:
        return []

    clients = Client.objects.filter(pk__in=client_ids.keys())
    today = timezone.now().date()

    result = []
    for client in clients:
        oldest = client_ids[client.pk]
        result.append(
            {
                "name": client.name,
                "phone": client.phone,
                "balance": client.outstanding_balance,
                "days_overdue": (today - oldest).days,
            }
        )

    # Du plus en retard au moins en retard
    result.sort(key=lambda x: x["days_overdue"], reverse=True)
    return result


def get_low_stock_products() -> list[dict]:
    """
    Retourne les produits actifs dont le stock est à ou en dessous du seuil.
    """
    from products.models import Product

    low = Product.objects.filter(
        is_active=True,
        stock_quantity__lte=F("low_stock_threshold"),
    ).order_by("stock_quantity")

    return [
        {
            "name": p.name,
            "category": p.category.name,
            "stock": p.stock_quantity,
            "threshold": p.low_stock_threshold,
        }
        for p in low
    ]


def generate_alerts_message(overdue_days: int = 30) -> str | None:
    """
    Génère le message d'alerte Telegram.
    Retourne None si aucune alerte à envoyer.
    """
    overdue_clients = get_overdue_clients(days=overdue_days)
    low_products = get_low_stock_products()

    if not overdue_clients and not low_products:
        return None

    today = timezone.now().date().strftime("%d/%m/%Y")
    lines = [f"🚨 <b>Alertes AquaTogo — {today}</b>", ""]

    # ── Clients en retard de paiement ─────────────────────────────────────────
    if overdue_clients:
        lines.append(f"💸 <b>Clients en retard de paiement ({len(overdue_clients)}) :</b>")
        for c in overdue_clients:
            lines.append(
                f"  • {c['name']} — <b>{c['balance']:,.0f} FCFA</b>"
                f" — en retard depuis <b>{c['days_overdue']} j</b>"
                f" 📞 {c['phone']}"
            )
        lines.append("")

    # ── Produits bientôt en rupture ───────────────────────────────────────────
    if low_products:
        lines.append(f"📦 <b>Stock faible ({len(low_products)}) :</b>")
        for p in low_products:
            stock_icon = "🔴" if p["stock"] == 0 else "🟠"
            lines.append(
                f"  {stock_icon} {p['name']} ({p['category']})"
                f" — stock : <b>{p['stock']}</b> / seuil : {p['threshold']}"
            )

    return "\n".join(lines)
