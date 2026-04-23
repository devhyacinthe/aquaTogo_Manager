from django.contrib import admin
from django.utils.html import format_html
from .models import Product, ProductCategory


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):

    # ── Liste ────────────────────────────────────────────────────────────────

    list_display = (
        "thumbnail",
        "name",
        "category",
        "purchase_price",
        "selling_price",
        "wholesale_price",
        "margin_display",
        "stock_quantity",
        "stock_status",
        "is_active",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")
    list_editable = ("stock_quantity", "is_active")
    list_per_page = 30
    ordering = ("category__name", "name")

    # ── Formulaire ───────────────────────────────────────────────────────────

    fieldsets = (
        (None, {
            "fields": ("name", "category", "description", "is_active"),
        }),
        ("Image", {
            "fields": ("image", "image_preview"),
        }),
        ("Prix", {
            "fields": ("purchase_price", "selling_price", "wholesale_price"),
        }),
        ("Stock", {
            "fields": ("stock_quantity", "low_stock_threshold"),
        }),
    )
    readonly_fields = ("image_preview", "created_at", "updated_at")

    # ── Actions ──────────────────────────────────────────────────────────────

    actions = ["mark_active", "mark_inactive"]

    @admin.action(description="Activer les produits sélectionnés")
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} produit(s) activé(s).")

    @admin.action(description="Désactiver les produits sélectionnés")
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} produit(s) désactivé(s).")

    # ── Colonnes calculées ───────────────────────────────────────────────────

    @admin.display(description="")
    def thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:48px; width:48px;'
                ' object-fit:cover; border-radius:4px;" />',
                obj.image.url,
            )
        return "—"

    @admin.display(description="Aperçu")
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:200px; max-width:300px;'
                ' object-fit:contain; border-radius:6px;" />',
                obj.image.url,
            )
        return "Aucune image."

    @admin.display(description="Marge")
    def margin_display(self, obj):
        color = "green" if obj.margin >= 0 else "red"
        return format_html(
            '<span style="color:{}">{} FCFA ({} %)</span>',
            color,
            obj.margin,
            obj.margin_percent,
        )

    @admin.display(description="Stock")
    def stock_status(self, obj):
        if obj.is_out_of_stock:
            label, color = "Rupture", "#c0392b"
        elif obj.is_low_stock:
            label, color = "Faible", "#e67e22"
        else:
            label, color = "OK", "#27ae60"
        return format_html(
            '<span style="font-weight:bold; color:{}">{}</span>',
            color,
            label,
        )
