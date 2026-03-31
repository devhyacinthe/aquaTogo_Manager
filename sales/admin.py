from django.contrib import admin
from django.utils.html import format_html
from .models import Sale, SaleItem, Payment


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1
    fields = (
        "product",
        "service",
        "quantity",
        "unit_price",
        "purchase_price_snapshot",
        "line_total",
        "line_profit",
    )
    readonly_fields = ("line_total", "line_profit")
    autocomplete_fields = ("product", "service")


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):

    # ── Liste ────────────────────────────────────────────────────────────────

    list_display = (
        "id",
        "client",
        "sale_date",
        "total_amount_display",
        "total_paid_display",
        "remaining_display",
        "payment_status_display",
        "created_by",
    )
    list_filter = ("payment_status", "sale_date", "created_by")
    search_fields = ("client__name", "created_by__username")
    list_per_page = 30
    date_hierarchy = "sale_date"
    ordering = ("-sale_date",)

    # ── Formulaire ───────────────────────────────────────────────────────────

    fieldsets = (
        (None, {
            "fields": ("client", "created_by", "sale_date"),
        }),
        ("Totaux", {
            "fields": ("total_amount", "total_profit", "payment_status"),
        }),
    )
    readonly_fields = ("total_amount", "total_profit", "payment_status", "created_at")
    inlines = [SaleItemInline]
    autocomplete_fields = ("client",)

    # ── Colonnes calculées ───────────────────────────────────────────────────

    @admin.display(description="Total facturé")
    def total_amount_display(self, obj):
        return f"{obj.total_amount} FCFA"

    @admin.display(description="Total payé")
    def total_paid_display(self, obj):
        return f"{obj.total_paid} FCFA"

    @admin.display(description="Reste dû")
    def remaining_display(self, obj):
        balance = obj.remaining_balance
        if balance > 0:
            return format_html(
                '<span style="color:#c0392b; font-weight:bold;">{} FCFA</span>',
                balance,
            )
        return "—"

    @admin.display(description="Statut")
    def payment_status_display(self, obj):
        colors = {
            Sale.PaymentStatus.PAID: "#27ae60",
            Sale.PaymentStatus.PARTIAL: "#e67e22",
            Sale.PaymentStatus.UNPAID: "#c0392b",
        }
        return format_html(
            '<span style="font-weight:bold; color:{}">{}</span>',
            colors[obj.payment_status],
            obj.get_payment_status_display(),
        )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    # ── Liste ────────────────────────────────────────────────────────────────

    list_display = (
        "id",
        "sale",
        "amount_display",
        "payment_method",
        "payment_date",
        "recorded_by",
    )
    list_filter = ("payment_method", "payment_date")
    search_fields = ("sale__client__name", "recorded_by__username", "note")
    list_per_page = 30
    date_hierarchy = "payment_date"
    ordering = ("-payment_date",)

    # ── Formulaire ───────────────────────────────────────────────────────────

    fieldsets = (
        (None, {
            "fields": ("sale", "recorded_by", "payment_date"),
        }),
        ("Détails", {
            "fields": ("amount", "payment_method", "note"),
        }),
    )
    autocomplete_fields = ("sale",)

    # ── Colonnes calculées ───────────────────────────────────────────────────

    @admin.display(description="Montant")
    def amount_display(self, obj):
        return f"{obj.amount} FCFA"
