from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import F

from .models import Product
from .forms import ProductForm


@login_required
def product_list(request):
    q = request.GET.get("q", "").strip()
    filtre = request.GET.get("filtre", "all")

    qs = Product.objects.filter(is_active=True)

    if q:
        qs = qs.filter(name__icontains=q)

    if filtre == "available":
        qs = qs.filter(stock_quantity__gt=F("low_stock_threshold"))
    elif filtre == "low":
        qs = qs.filter(stock_quantity__gt=0, stock_quantity__lte=F("low_stock_threshold"))
    elif filtre == "out":
        qs = qs.filter(stock_quantity=0)

    qs = qs.order_by("category", "name")

    all_active = Product.objects.filter(is_active=True)
    low_stock_count = all_active.filter(
        stock_quantity__gt=0, stock_quantity__lte=F("low_stock_threshold")
    ).count()
    out_of_stock_count = all_active.filter(stock_quantity=0).count()

    return render(
        request,
        "products/list.html",
        {
            "products": qs,
            "q": q,
            "filtre": filtre,
            "total_count": all_active.count(),
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
            "is_staff": request.user.is_staff,
        },
    )


@login_required
def product_create(request):
    if not request.user.is_staff:
        raise PermissionDenied

    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            messages.success(request, f"Produit \u00ab\u00a0{product.name}\u00a0\u00bb cr\u00e9\u00e9 avec succ\u00e8s.")
            return redirect("products:detail", pk=product.pk)
    else:
        form = ProductForm()

    return render(request, "products/form.html", {"form": form, "is_edit": False})


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)

    from sales.models import SaleItem

    sale_history = (
        SaleItem.objects.filter(product=product)
        .select_related("sale", "sale__client")
        .order_by("-sale__sale_date", "-sale__id")[:10]
    )

    return render(
        request,
        "products/detail.html",
        {
            "product": product,
            "sale_history": sale_history,
            "is_staff": request.user.is_staff,
        },
    )


@login_required
def product_edit(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied

    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        clear_image = request.POST.get("clear_image") == "1"
        if clear_image and product.image:
            product.image.delete(save=False)
            product.image = None

        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            saved = form.save(commit=False)
            if clear_image:
                saved.image = None
            saved.save()
            messages.success(request, f"Produit \u00ab\u00a0{saved.name}\u00a0\u00bb modifi\u00e9 avec succ\u00e8s.")
            return redirect("products:detail", pk=saved.pk)
    else:
        form = ProductForm(instance=product)

    return render(
        request,
        "products/form.html",
        {"form": form, "is_edit": True, "product": product},
    )


@login_required
def product_delete(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied

    if request.method != "POST":
        return redirect("products:detail", pk=pk)

    product = get_object_or_404(Product, pk=pk)
    name = product.name
    product.is_active = False
    product.save(update_fields=["is_active"])
    messages.success(request, f"Produit \u00ab\u00a0{name}\u00a0\u00bb archiv\u00e9 avec succ\u00e8s.")
    return redirect("products:list")


@login_required
def product_adjust_stock(request, pk):
    if request.method != "POST":
        return redirect("products:detail", pk=pk)

    product = get_object_or_404(Product, pk=pk)
    action = request.POST.get("action", "add")
    try:
        quantity = int(request.POST.get("quantity", 0))
        if quantity <= 0:
            raise ValueError("La quantit\u00e9 doit \u00eatre un entier positif.")
        if action == "add":
            product.increase_stock(quantity)
            # Créer automatiquement une dépense "Achat de stock"
            from datetime import date
            from accounting.models import Expense
            expense_amount = product.purchase_price * quantity
            Expense.objects.create(
                label=f"Réapprovisionnement : {product.name} × {quantity}",
                category=Expense.Category.STOCK,
                amount=expense_amount,
                expense_date=date.today(),
                note=f"Ajustement de stock automatique (+{quantity} unité(s)).",
            )
            messages.success(
                request,
                f"Stock mis à jour : +{quantity} unité(s). Nouveau stock : {product.stock_quantity}. "
                f"Dépense de {expense_amount:,.0f} FCFA enregistrée.",
            )
        elif action == "subtract":
            product.decrease_stock(quantity)
            messages.success(
                request,
                f"Stock mis \u00e0 jour\u00a0: -{quantity} unit\u00e9(s). Nouveau stock\u00a0: {product.stock_quantity}.",
            )
        else:
            messages.error(request, "Action invalide.")
    except (ValueError, TypeError) as e:
        messages.error(request, str(e))

    return redirect("products:detail", pk=pk)
