import json as _json
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from clients.models import Client
from products.models import Product
from services.models import Service

from .models import Quote, QuoteItem


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_decimal(value, default=Decimal("0.00")):
    try:
        return Decimal(str(value))
    except Exception:
        return default


# ── quote_list ────────────────────────────────────────────────────────────────

@login_required
def quote_list(request):
    status_filter = request.GET.get("status", "")
    qs = Quote.objects.select_related("client", "created_by").prefetch_related("items")
    if status_filter:
        qs = qs.filter(status=status_filter)

    counts = {s.value: Quote.objects.filter(status=s.value).count() for s in Quote.Status}
    counts["all"] = Quote.objects.count()

    return render(request, "devis/list.html", {
        "quotes": qs,
        "status_filter": status_filter,
        "counts": counts,
        "Status": Quote.Status,
    })


# ── quote_create ──────────────────────────────────────────────────────────────

@login_required
def quote_create(request):
    products = Product.objects.filter(is_active=True).select_related("category").order_by("name")
    services = Service.objects.filter(is_active=True).order_by("name")

    products_data = [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category.name,
            "category_key": p.category.slug,
            "selling_price": str(p.selling_price),
            "purchase_price": str(p.purchase_price),
            "stock_quantity": p.stock_quantity,
            "is_out_of_stock": p.is_out_of_stock,
        }
        for p in products
    ]
    services_data = [
        {"id": s.id, "name": s.name, "price": str(s.price)}
        for s in services
    ]

    if request.method == "POST":
        cart_raw    = request.POST.get("cart_data", "")
        client_id   = request.POST.get("client_id", "").strip()
        valid_until = request.POST.get("valid_until", "").strip() or None
        note        = request.POST.get("note", "").strip()

        try:
            cart = _json.loads(cart_raw) if cart_raw else []
        except _json.JSONDecodeError:
            cart = []

        if not cart:
            return render(request, "devis/create.html", {
                "products_data": products_data,
                "services_data": services_data,
                "error": "Le devis est vide.",
            })

        client = None
        if client_id:
            try:
                client = Client.objects.get(pk=int(client_id), is_active=True)
            except (Client.DoesNotExist, ValueError):
                pass

        quote = Quote.objects.create(
            client=client,
            status=Quote.Status.DRAFT,
            valid_until=valid_until,
            note=note,
            total_amount=Decimal("0.00"),
            created_by=request.user,
        )

        total = Decimal("0.00")
        for item in cart:
            try:
                unit_price = _parse_decimal(item.get("unit_price"))
                qty        = int(item.get("qty", 1))
            except (ValueError, TypeError):
                continue

            product = service = None
            label = item.get("name", "Article")
            if item.get("type") == "product":
                product = Product.objects.filter(pk=item.get("id")).first()
            elif item.get("type") == "service":
                service = Service.objects.filter(pk=item.get("id")).first()

            QuoteItem.objects.create(
                quote=quote,
                product=product,
                service=service,
                label=label,
                unit_price=unit_price,
                quantity=qty,
            )
            total += unit_price * qty

        quote.total_amount = total
        quote.save(update_fields=["total_amount"])

        return redirect("devis:detail", pk=quote.pk)

    return render(request, "devis/create.html", {
        "products_data": products_data,
        "services_data": services_data,
        "today": date.today().isoformat(),
    })


# ── quote_detail ──────────────────────────────────────────────────────────────

@login_required
def quote_detail(request, pk):
    quote = get_object_or_404(
        Quote.objects.select_related("client", "created_by", "converted_sale"),
        pk=pk,
    )
    items = quote.items.select_related("product", "service").all()
    return render(request, "devis/detail.html", {
        "quote": quote,
        "items": items,
        "Status": Quote.Status,
    })


# ── quote_update_status ───────────────────────────────────────────────────────

@login_required
@require_POST
def quote_update_status(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    new_status = request.POST.get("status", "")
    allowed = [Quote.Status.DRAFT, Quote.Status.SENT, Quote.Status.ACCEPTED, Quote.Status.REJECTED]
    if new_status in [s.value for s in allowed]:
        quote.status = new_status
        quote.save(update_fields=["status"])
    return redirect("devis:detail", pk=pk)


# ── quote_convert ─────────────────────────────────────────────────────────────

@login_required
@require_POST
def quote_convert(request, pk):
    from django.db import transaction
    from sales.models import Sale, SaleItem

    quote = get_object_or_404(Quote, pk=pk)
    if quote.status == Quote.Status.CONVERTED:
        return redirect("devis:detail", pk=pk)

    with transaction.atomic():
        sale = Sale.objects.create(
            client=quote.client,
            created_by=request.user,
            sale_date=date.today(),
        )
        for item in quote.items.select_related("product", "service").all():
            purchase_price = Decimal("0.00")
            if item.product:
                purchase_price = item.product.purchase_price

            si = SaleItem(
                sale=sale,
                product=item.product,
                service=item.service,
                label=item.label,
                quantity=item.quantity,
                unit_price=item.unit_price,
                purchase_price_snapshot=purchase_price,
            )
            # call save() directly so stock is decremented
            si.save()

        sale.recompute_totals()
        quote.status = Quote.Status.CONVERTED
        quote.converted_sale = sale
        quote.save(update_fields=["status", "converted_sale"])

    return redirect("sales:detail", pk=sale.pk)


# ── quote_pdf ─────────────────────────────────────────────────────────────────

@login_required
def quote_pdf(request, pk):
    import os
    from io import BytesIO
    from django.conf import settings as django_settings
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image,
    )
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER

    quote = get_object_or_404(Quote, pk=pk)
    items = list(quote.items.select_related("product", "service").all())

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
    )

    brand = colors.HexColor("#0EA5E9")
    gray  = colors.HexColor("#6B7280")
    light = colors.HexColor("#F0F9FF")

    def _p(text, **kw):
        return Paragraph(text, ParagraphStyle("_", **kw))

    def _fmt(n):
        return f"{n:,.0f}".replace(",", "\u202f")

    story = []

    # ── En-tête ───────────────────────────────────────────────────────────────
    logo_path = os.path.join(django_settings.BASE_DIR, "static", "img", "logo.png")
    if os.path.exists(logo_path):
        logo_cell = Image(logo_path, width=1.4 * cm, height=1.4 * cm)
        name_cell = _p(
            '<font size="18" color="#0EA5E9"><b>AquaTogo</b></font><br/>'
            '<font size="9" color="#6B7280">Produits et services d\'aquariophilie</font>',
        )
        left_col = Table([[logo_cell, name_cell]], colWidths=[1.6 * cm, 8 * cm])
        left_col.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (1, 0), (1, 0), 6),
        ]))
    else:
        left_col = _p(
            '<font size="18" color="#0EA5E9"><b>AquaTogo</b></font><br/>'
            '<font size="9" color="#6B7280">Produits et services d\'aquariophilie</font>',
        )

    date_str = quote.created_at.strftime("%d/%m/%Y")
    valid_str = quote.valid_until.strftime("%d/%m/%Y") if quote.valid_until else "—"
    header_data = [[
        left_col,
        _p(
            f'<font size="9" color="#6B7280">'
            f'Date : {date_str}<br/>'
            f'Validité : {valid_str}<br/>'
            f'Établi par : {quote.created_by.get_full_name() or quote.created_by.username}'
            f'</font>',
            alignment=TA_RIGHT,
        ),
    ]]
    ht = Table(header_data, colWidths=[10 * cm, 7.5 * cm])
    ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(ht)
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=brand))
    story.append(Spacer(1, 0.5 * cm))

    # ── Numéro + client ───────────────────────────────────────────────────────
    client_name  = quote.client.name  if quote.client else "Client anonyme"
    client_phone = getattr(quote.client, "phone", "") if quote.client else ""
    status_label = quote.get_status_display()
    status_colors_map = {
        "draft":     "#6B7280",
        "sent":      "#D97706",
        "accepted":  "#15803D",
        "rejected":  "#DC2626",
        "converted": "#0EA5E9",
    }
    s_color = status_colors_map.get(quote.status, "#374151")

    info_data = [[
        _p(
            f'<font size="14"><b>DEVIS N° {quote.pk:04d}</b></font><br/>'
            f'<font size="9" color="{s_color}"><b>● {status_label}</b></font>'
        ),
        _p(
            '<b>Client</b><br/>'
            f'<font size="10">{client_name}</font>'
            + (f'<br/><font size="9" color="#6B7280">Tél : {client_phone}</font>' if client_phone else "")
        ),
    ]]
    it = Table(info_data, colWidths=[9 * cm, 8.5 * cm])
    it.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND",    (1, 0), (1, 0),   light),
        ("LEFTPADDING",   (1, 0), (1, 0),   10),
        ("TOPPADDING",    (1, 0), (1, 0),   8),
        ("BOTTOMPADDING", (1, 0), (1, 0),   8),
        ("RIGHTPADDING",  (1, 0), (1, 0),   10),
    ]))
    story.append(it)
    story.append(Spacer(1, 0.7 * cm))

    # ── Tableau articles ──────────────────────────────────────────────────────
    rows = [[
        _p("<b>Article</b>",           fontSize=9),
        _p("<b>Qté</b>",               fontSize=9, alignment=TA_RIGHT),
        _p("<b>Prix unit. (FCFA)</b>", fontSize=9, alignment=TA_RIGHT),
        _p("<b>Total (FCFA)</b>",      fontSize=9, alignment=TA_RIGHT),
    ]]
    for item in items:
        rows.append([
            _p(item.label, fontSize=9),
            _p(str(item.quantity), fontSize=9, alignment=TA_RIGHT),
            _p(_fmt(item.unit_price), fontSize=9, alignment=TA_RIGHT),
            _p(_fmt(item.line_total), fontSize=9, alignment=TA_RIGHT),
        ])
    rows.append([
        "", "",
        _p("<b>TOTAL</b>",                                           fontSize=10, alignment=TA_RIGHT),
        _p(f"<b>{_fmt(quote.total_amount)} FCFA</b>", fontSize=10, alignment=TA_RIGHT),
    ])

    at = Table(rows, colWidths=[9.5 * cm, 2 * cm, 3.5 * cm, 3.5 * cm])
    at.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  brand),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BACKGROUND",   (0, -1), (-1, -1), light),
        ("LINEABOVE",    (0, -1), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(at)

    # ── Note ──────────────────────────────────────────────────────────────────
    if quote.note:
        story.append(Spacer(1, 0.6 * cm))
        story.append(_p("<b>Note :</b>", fontSize=9))
        story.append(Spacer(1, 0.15 * cm))
        story.append(_p(quote.note, fontSize=9, textColor=gray))

    # ── Pied de page ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.2 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 0.3 * cm))
    story.append(_p(
        "AquaTogo — Ce devis est valable jusqu'au " + valid_str + " · Merci de votre confiance !",
        fontSize=8, textColor=gray, alignment=TA_CENTER,
    ))

    doc.build(story)
    buffer.seek(0)

    filename = f"Devis_AquaTogo_{quote.pk:04d}_{quote.created_at.strftime('%Y%m%d')}.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
