import json as _json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from clients.models import Client
from products.models import Product
from services.models import Service

from .models import Payment, Sale, SaleItem


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_decimal(value, default=Decimal("0.00")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


# ── sale_list ─────────────────────────────────────────────────────────────────

@login_required
def sale_list(request):
    periode = request.GET.get("periode", "today")
    today = date.today()

    if periode == "week":
        start = today - timedelta(days=today.weekday())
        end = today
    elif periode == "month":
        start = today.replace(day=1)
        end = today
    else:
        periode = "today"
        start = today
        end = today

    sales = (
        Sale.objects.filter(sale_date__gte=start, sale_date__lte=end)
        .select_related("client", "created_by")
        .prefetch_related("items")
    )

    aggregates = sales.aggregate(
        total_ca=Sum("total_amount"),
        total_profit=Sum("total_profit"),
    )
    total_ca = aggregates["total_ca"] or Decimal("0.00")
    total_profit = aggregates["total_profit"] or Decimal("0.00")

    return render(request, "sales/list.html", {
        "sales": sales,
        "period": periode,
        "today": today,
        "total_ca": total_ca,
        "total_profit": total_profit,
    })


# ── sale_create ───────────────────────────────────────────────────────────────

@login_required
def sale_create(request):
    products = Product.objects.filter(is_active=True).order_by("name")
    services = Service.objects.filter(is_active=True).order_by("name")

    products_data = [
        {
            "id": p.id,
            "name": p.name,
            "category": p.get_category_display(),
            "selling_price": str(p.selling_price),
            "purchase_price": str(p.purchase_price),
            "stock_quantity": p.stock_quantity,
            "is_out_of_stock": p.is_out_of_stock,
        }
        for p in products
    ]
    services_data = [
        {
            "id": s.id,
            "name": s.name,
            "price": str(s.price),
        }
        for s in services
    ]

    if request.method == "POST":
        cart_raw = request.POST.get("cart_data", "")
        client_id = request.POST.get("client_id", "").strip()
        payment_amount_raw = request.POST.get("payment_amount", "").strip()
        payment_method = request.POST.get("payment_method", "cash")

        # Parse cart
        try:
            cart = _json.loads(cart_raw) if cart_raw else []
        except _json.JSONDecodeError:
            cart = []

        if not cart:
            return render(request, "sales/create.html", {
                "products_data": products_data,
                "services_data": services_data,
                "error": "Le panier est vide.",
            })

        # Resolve client
        client = None
        if client_id:
            try:
                client = Client.objects.get(pk=int(client_id), is_active=True)
            except (Client.DoesNotExist, ValueError):
                client = None

        # Validate: services require a client
        has_services = any(item.get("type") == "service" for item in cart)
        if has_services and not client:
            return render(request, "sales/create.html", {
                "products_data": products_data,
                "services_data": services_data,
                "error": "Un client est requis pour enregistrer des prestations de service.",
            })

        try:
            with transaction.atomic():
                from services.models import ServiceExecution

                sale = Sale.objects.create(
                    client=client,
                    created_by=request.user,
                    sale_date=date.today(),
                )

                for item in cart:
                    item_type = item.get("type")
                    item_id = item.get("id")
                    qty = int(item.get("qty", 1))
                    unit_price = _parse_decimal(item.get("unit_price"))
                    purchase_price = _parse_decimal(item.get("purchase_price", "0"))

                    if item_type == "product":
                        product = Product.objects.select_for_update().get(pk=item_id)
                        SaleItem.objects.create(
                            sale=sale,
                            product=product,
                            quantity=qty,
                            unit_price=unit_price,
                            purchase_price_snapshot=purchase_price,
                        )
                    elif item_type == "service":
                        service_obj = Service.objects.get(pk=item_id)
                        sale_item = SaleItem.objects.create(
                            sale=sale,
                            service=service_obj,
                            quantity=qty,
                            unit_price=unit_price,
                            purchase_price_snapshot=Decimal("0.00"),
                        )
                        # Create linked ServiceExecution for renewal tracking
                        ServiceExecution.objects.create(
                            client=client,
                            service=service_obj,
                            sale_item=sale_item,
                            execution_date=sale.sale_date,
                        )

                sale.recompute_totals()

                # Optional immediate payment
                payment_amount = _parse_decimal(payment_amount_raw)
                if payment_amount > Decimal("0.00"):
                    # Cap at total
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
                        payment_date=date.today(),
                    )

        except ValueError as e:
            return render(request, "sales/create.html", {
                "products_data": products_data,
                "services_data": services_data,
                "error": str(e),
            })
        except Exception as e:
            return render(request, "sales/create.html", {
                "products_data": products_data,
                "services_data": services_data,
                "error": f"Erreur lors de la création de la vente : {e}",
            })

        return redirect("sales:detail", pk=sale.pk)

    return render(request, "sales/create.html", {
        "products_data": products_data,
        "services_data": services_data,
    })


# ── sale_detail ───────────────────────────────────────────────────────────────

@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related("client", "created_by")
        .prefetch_related("items__product", "items__service", "payments__recorded_by"),
        pk=pk,
    )
    return render(request, "sales/detail.html", {"sale": sale})


# ── sale_add_payment ──────────────────────────────────────────────────────────

@login_required
@require_POST
def sale_add_payment(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    amount = _parse_decimal(request.POST.get("amount", "0"))
    payment_method = request.POST.get("payment_method", "cash")

    if amount > Decimal("0.00"):
        remaining = sale.remaining_balance
        if amount > remaining:
            amount = remaining
        valid_methods = [m[0] for m in Payment.Method.choices]
        if payment_method not in valid_methods:
            payment_method = "cash"
        Payment.objects.create(
            sale=sale,
            recorded_by=request.user,
            amount=amount,
            payment_method=payment_method,
            payment_date=date.today(),
        )

    return redirect("sales:detail", pk=pk)


# ── API views ─────────────────────────────────────────────────────────────────

@login_required
@require_GET
def api_clients(request):
    q = request.GET.get("q", "").strip()
    qs = Client.objects.filter(is_active=True)
    if q:
        qs = qs.filter(name__icontains=q)
    data = list(qs.values("id", "name", "phone")[:15])
    return JsonResponse(data, safe=False)


@login_required
@require_GET
def api_products(_request):
    products = Product.objects.filter(is_active=True).order_by("name")
    data = [
        {
            "id": p.id,
            "name": p.name,
            "category": p.get_category_display(),
            "selling_price": str(p.selling_price),
            "purchase_price": str(p.purchase_price),
            "stock_quantity": p.stock_quantity,
            "is_out_of_stock": p.is_out_of_stock,
        }
        for p in products
    ]
    return JsonResponse(data, safe=False)


@login_required
@require_GET
def api_services(_request):
    services = Service.objects.filter(is_active=True).order_by("name")
    data = [
        {
            "id": s.id,
            "name": s.name,
            "price": str(s.price),
        }
        for s in services
    ]
    return JsonResponse(data, safe=False)
