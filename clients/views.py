import re
from datetime import date as _date
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Value, DecimalField, F, ExpressionWrapper, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.views.decorators.http import require_POST

from .models import Client
from .forms import ClientForm


def _annotate_clients(qs):
    """Annotate a Client queryset with ann_total, ann_paid, ann_balance.

    Uses subqueries instead of multi-table JOINs to avoid the SUM(DISTINCT)
    deduplication bug (two sales with the same amount would only be counted once).
    Also excludes canceled sales.
    """
    from sales.models import Sale, Payment

    _zero = Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))
    _df   = DecimalField(max_digits=14, decimal_places=2)

    total_sq = (
        Sale.objects
        .filter(client=OuterRef("pk"), status="active")
        .values("client")
        .annotate(t=Sum("total_amount"))
        .values("t")
    )
    paid_sq = (
        Payment.objects
        .filter(sale__client=OuterRef("pk"), sale__status="active")
        .values("sale__client")
        .annotate(p=Sum("amount"))
        .values("p")
    )

    return qs.annotate(
        ann_total=Coalesce(Subquery(total_sq, output_field=_df), _zero, output_field=_df),
        ann_paid =Coalesce(Subquery(paid_sq,  output_field=_df), _zero, output_field=_df),
    ).annotate(
        ann_balance=ExpressionWrapper(
            F("ann_total") - F("ann_paid"),
            output_field=_df,
        )
    )


@login_required
def client_list(request):
    q = request.GET.get("q", "").strip()
    filtre = request.GET.get("filtre", "all")

    base_qs = Client.objects.filter(is_active=True)
    if q:
        base_qs = base_qs.filter(Q(name__icontains=q) | Q(phone__icontains=q))

    clients = _annotate_clients(base_qs)

    if filtre == "debtors":
        clients = clients.filter(ann_balance__gt=0).order_by("-ann_balance")
    else:
        clients = clients.order_by("name")

    total_count = Client.objects.filter(is_active=True).count()
    debtors_count = (
        _annotate_clients(Client.objects.filter(is_active=True))
        .filter(ann_balance__gt=0)
        .count()
    )

    context = {
        "clients": clients,
        "q": q,
        "filtre": filtre,
        "total_count": total_count,
        "debtors_count": debtors_count,
        "is_staff": request.user.is_staff,
        "app_name": "clients",
    }
    return render(request, "clients/list.html", context)


@login_required
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, f"Client « {client.name} » ajouté avec succès.")
            return redirect("clients:detail", pk=client.pk)
    else:
        form = ClientForm()

    context = {
        "form": form,
        "title": "Nouveau client",
        "submit_label": "Créer le client",
        "app_name": "clients",
    }
    return render(request, "clients/form.html", context)


@login_required
def client_detail(request, pk):
    from services.models import ServiceExecution

    client = get_object_or_404(Client, pk=pk)

    sales = (
        client.sales
        .select_related("created_by")
        .prefetch_related("items__product", "items__service", "payments")
        .order_by("-sale_date", "-id")[:20]
    )

    service_executions = (
        ServiceExecution.objects
        .filter(client=client)
        .select_related("service")
        .order_by("-execution_date")[:10]
    )

    upcoming = client.upcoming_service_executions(days=30)
    phone_digits = re.sub(r"\D", "", client.phone) if client.phone else ""

    context = {
        "client": client,
        "sales": sales,
        "service_executions": service_executions,
        "upcoming": upcoming,
        "phone_digits": phone_digits,
        "today": _date.today(),
        "is_staff": request.user.is_staff,
        "app_name": "clients",
    }
    return render(request, "clients/detail.html", context)


@login_required
@require_POST
def client_settle_debt(request, pk):
    """
    Distribue un paiement sur les ventes impayées/partielles du client,
    des plus anciennes aux plus récentes.
    """
    from sales.models import Payment

    client = get_object_or_404(Client, pk=pk)

    # ── Montant ───────────────────────────────────────────────────────────────
    try:
        amount = Decimal(request.POST.get("amount", "0").strip())
    except InvalidOperation:
        amount = Decimal("0")

    if amount <= 0:
        messages.error(request, "Le montant doit être supérieur à 0.")
        return redirect("clients:detail", pk=pk)

    balance = client.outstanding_balance
    if amount > balance:
        messages.error(
            request,
            f"Le montant ({amount:,.0f} FCFA) dépasse le solde dû ({balance:,.0f} FCFA)."
        )
        return redirect("clients:detail", pk=pk)

    # ── Méthode & date ────────────────────────────────────────────────────────
    payment_method = request.POST.get("payment_method", "cash")
    valid_methods = [m[0] for m in Payment.Method.choices]
    if payment_method not in valid_methods:
        payment_method = "cash"

    raw_date = request.POST.get("payment_date", "").strip()
    try:
        pay_date = _date.fromisoformat(raw_date) if raw_date else _date.today()
    except ValueError:
        pay_date = _date.today()

    # ── Distribution sur les ventes impayées (plus anciennes en premier) ──────
    unpaid_sales = (
        client.sales
        .filter(payment_status__in=["unpaid", "partial"])
        .order_by("sale_date", "id")
    )

    remaining = amount
    payments_created = 0

    try:
        with transaction.atomic():
            for sale in unpaid_sales:
                if remaining <= 0:
                    break
                to_pay = min(remaining, sale.remaining_balance)
                if to_pay > 0:
                    Payment.objects.create(
                        sale=sale,
                        recorded_by=request.user,
                        amount=to_pay,
                        payment_method=payment_method,
                        payment_date=pay_date,
                    )
                    remaining -= to_pay
                    payments_created += 1

        messages.success(
            request,
            f"{amount:,.0f} FCFA encaissés sur {payments_created} vente{'' if payments_created == 1 else 's'}."
        )
    except Exception as e:
        messages.error(request, f"Erreur lors de l'enregistrement : {e}")

    return redirect("clients:detail", pk=pk)


@login_required
@require_POST
def client_delete(request, pk):
    if not request.user.is_staff:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    client = get_object_or_404(Client, pk=pk)
    name = client.name
    client.is_active = False
    client.save(update_fields=["is_active"])
    messages.success(request, f"Client « {name} » supprimé.")
    return redirect("clients:list")


@login_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)

    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f"Client « {client.name} » mis à jour.")
            return redirect("clients:detail", pk=client.pk)
    else:
        form = ClientForm(instance=client)

    context = {
        "form": form,
        "client": client,
        "title": f"Modifier « {client.name} »",
        "submit_label": "Enregistrer les modifications",
        "app_name": "clients",
    }
    return render(request, "clients/form.html", context)


# ── client_invoice_pdf ────────────────────────────────────────────────────────

@login_required
def client_invoice_pdf(request, pk):
    """Facture consolidée : toutes les ventes actives d'un client."""
    import os
    from io import BytesIO
    from django.conf import settings
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image,
    )
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from sales.models import Sale, Payment

    client = get_object_or_404(Client, pk=pk)
    sales = list(
        client.sales
        .filter(status="active")
        .prefetch_related("items__product", "items__service", "payments")
        .order_by("sale_date", "id")
    )
    if not sales:
        messages.info(request, "Aucune vente active pour ce client.")
        return redirect("clients:detail", pk=pk)

    # Agrégats
    grand_total = sum(s.total_amount for s in sales)
    all_payments = []
    for s in sales:
        all_payments.extend(list(s.payments.all()))
    all_payments.sort(key=lambda p: (p.payment_date, p.pk))
    total_paid = sum(p.amount for p in all_payments)
    remaining = grand_total - total_paid

    # Statut global
    if remaining <= 0:
        global_status = "paid"
    elif total_paid > 0:
        global_status = "partial"
    else:
        global_status = "unpaid"

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
    )

    brand = colors.HexColor("#0EA5E9")
    gray  = colors.HexColor("#6B7280")
    light = colors.HexColor("#F0F9FF")

    def _p(text, **kw):
        return Paragraph(text, ParagraphStyle("_", **kw))

    def _fmt(n):
        return f"{n:,.0f}".replace(",", "\u202f")

    story = []

    # ── En-tête boutique ──────────────────────────────────────────────────────
    logo_path = os.path.join(settings.BASE_DIR, "static", "img", "logo.png")
    if os.path.exists(logo_path):
        logo_cell = Image(logo_path, width=1.4 * cm, height=1.4 * cm)
        name_cell = _p(
            '<font size="18" color="#0EA5E9"><b>AquaTogo</b></font><br/>'
            '<font size="9" color="#6B7280">Produits et services d\'aquariophilie</font>',
        )
        left_col = Table([[logo_cell, name_cell]], colWidths=[1.6 * cm, 8 * cm])
        left_col.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (1, 0), (1, 0), 6)]))
    else:
        left_col = _p(
            '<font size="18" color="#0EA5E9"><b>AquaTogo</b></font><br/>'
            '<font size="9" color="#6B7280">Produits et services d\'aquariophilie</font>',
        )

    header_data = [[
        left_col,
        _p(f'<font size="9" color="#6B7280">Date : {_date.today().strftime("%d/%m/%Y")}</font>',
           alignment=TA_RIGHT),
    ]]
    ht = Table(header_data, colWidths=[10 * cm, 7.5 * cm])
    ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(ht)
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=brand))
    story.append(Spacer(1, 0.5 * cm))

    # ── Titre + Client ────────────────────────────────────────────────────────
    status_colors = {"paid": "#15803D", "partial": "#D97706", "unpaid": "#DC2626"}
    status_labels = {"paid": "PAYÉ", "partial": "PARTIELLEMENT PAYÉ", "unpaid": "IMPAYÉ"}
    s_color = status_colors.get(global_status, "#374151")
    s_label = status_labels.get(global_status, "")

    client_phone = client.phone or ""
    info_data = [[
        _p(f'<font size="14"><b>FACTURE CLIENT</b></font><br/>'
           f'<font size="9" color="{s_color}"><b>● {s_label}</b></font>'),
        _p(f'<b>{client.name}</b>'
           + (f'<br/><font size="9" color="#6B7280">Tél : {client_phone}</font>' if client_phone else "")),
    ]]
    it = Table(info_data, colWidths=[9 * cm, 8.5 * cm])
    it.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (1, 0), (1, 0), light),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("TOPPADDING", (1, 0), (1, 0), 8),
        ("BOTTOMPADDING", (1, 0), (1, 0), 8),
        ("RIGHTPADDING", (1, 0), (1, 0), 10),
    ]))
    story.append(it)
    story.append(Spacer(1, 0.7 * cm))

    # ── Tableau de tous les articles ──────────────────────────────────────────
    rows = [[
        _p("<b>Article</b>", fontSize=9),
        _p("<b>Vente</b>", fontSize=9),
        _p("<b>Qté</b>", fontSize=9, alignment=TA_RIGHT),
        _p("<b>Prix unit.</b>", fontSize=9, alignment=TA_RIGHT),
        _p("<b>Total (FCFA)</b>", fontSize=9, alignment=TA_RIGHT),
    ]]
    for sale in sales:
        for item in sale.items.all():
            name = (item.product.name if item.product
                    else (item.service.name if item.service
                          else (item.label or "—")))
            rows.append([
                _p(name, fontSize=9),
                _p(f"#{sale.pk:04d}", fontSize=8, textColor=gray),
                _p(str(item.quantity), fontSize=9, alignment=TA_RIGHT),
                _p(_fmt(item.unit_price), fontSize=9, alignment=TA_RIGHT),
                _p(_fmt(item.line_total), fontSize=9, alignment=TA_RIGHT),
            ])

    # Ligne Total
    rows.append([
        "", "", "",
        _p("<b>TOTAL</b>", fontSize=10, alignment=TA_RIGHT),
        _p(f"<b>{_fmt(grand_total)} FCFA</b>", fontSize=10, alignment=TA_RIGHT),
    ])

    at = Table(rows, colWidths=[6.5 * cm, 2 * cm, 2 * cm, 3.5 * cm, 3.5 * cm])
    at.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), brand),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS",(0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BACKGROUND",    (0, -1), (-1, -1), light),
        ("LINEABOVE",     (0, -1), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(at)
    story.append(Spacer(1, 0.6 * cm))

    # ── Paiements reçus ──────────────────────────────────────────────────────
    if all_payments:
        story.append(_p("<b>Paiements reçus</b>", fontSize=10))
        story.append(Spacer(1, 0.25 * cm))

        pay_rows = [[
            _p("<b>Date</b>", fontSize=9),
            _p("<b>Méthode</b>", fontSize=9),
            _p("<b>Vente</b>", fontSize=9),
            _p("<b>Montant (FCFA)</b>", fontSize=9, alignment=TA_RIGHT),
        ]]
        for p in all_payments:
            pay_rows.append([
                _p(p.payment_date.strftime("%d/%m/%Y"), fontSize=9),
                _p(p.get_payment_method_display(), fontSize=9),
                _p(f"#{p.sale.pk:04d}", fontSize=8, textColor=gray),
                _p(_fmt(p.amount), fontSize=9, alignment=TA_RIGHT),
            ])

        # Résumé
        if remaining > 0:
            pay_rows.append([
                "", "",
                _p("<b>Total payé</b>", fontSize=9, alignment=TA_RIGHT),
                _p(f'<font color="#15803D"><b>{_fmt(total_paid)} FCFA</b></font>',
                   fontSize=9, alignment=TA_RIGHT),
            ])
            pay_rows.append([
                "", "",
                _p("<b>Reste à payer</b>", fontSize=9, alignment=TA_RIGHT),
                _p(f'<font color="#DC2626"><b>{_fmt(remaining)} FCFA</b></font>',
                   fontSize=9, alignment=TA_RIGHT),
            ])

        n_rows = len(pay_rows)
        pt = Table(pay_rows, colWidths=[3.5 * cm, 4.5 * cm, 3.5 * cm, 4 * cm])
        ts = [
            ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#F1F5F9")),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("ALIGN",         (3, 0), (3, -1),  "RIGHT"),
        ]
        if remaining > 0:
            ts += [
                ("BACKGROUND", (0, n_rows - 1), (-1, n_rows - 1), colors.HexColor("#FEF2F2")),
                ("LINEABOVE",  (0, n_rows - 1), (-1, n_rows - 1), 0.5, colors.HexColor("#FCA5A5")),
            ]
        pt.setStyle(TableStyle(ts))
        story.append(pt)

    # ── Pied de page ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.2 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 0.3 * cm))
    story.append(_p("AquaTogo — Merci pour votre confiance !",
                    fontSize=8, textColor=gray, alignment=TA_CENTER))

    # ── Tampon PAYÉ ───────────────────────────────────────────────────────────
    if global_status == "paid":
        def _draw_paid_stamp(canvas, doc):
            canvas.saveState()
            canvas.setFillAlpha(0.25)
            canvas.setStrokeAlpha(0.25)
            stamp_green = colors.HexColor("#15803D")
            canvas.setFillColor(stamp_green)
            canvas.setStrokeColor(stamp_green)
            canvas.setLineWidth(5)
            canvas.setFont("Helvetica-Bold", 62)
            w, h = A4
            canvas.translate(w / 2, h / 2)
            canvas.rotate(42)
            canvas.roundRect(-108, -36, 216, 72, 10, fill=0, stroke=1)
            canvas.drawCentredString(0, -22, "PAYÉ")
            canvas.restoreState()
        doc.build(story, onFirstPage=_draw_paid_stamp, onLaterPages=_draw_paid_stamp)
    else:
        doc.build(story)
    buffer.seek(0)

    filename = f"Facture_Client_{client.name.replace(' ', '_')}_{_date.today().strftime('%Y%m%d')}.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
