from django.contrib import admin
from django.utils.html import format_html
from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):

    # ── Liste ────────────────────────────────────────────────────────────────

    list_display = (
        "name",
        "phone",
        "total_purchases_display",
        "outstanding_balance_display",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "phone", "notes")
    list_editable = ("is_active",)
    list_per_page = 30
    ordering = ("name",)

    # ── Formulaire ───────────────────────────────────────────────────────────

    fieldsets = (
        (None, {
            "fields": ("name", "phone", "is_active"),
        }),
        ("Notes", {
            "fields": ("notes",),
            "classes": ("collapse",),
        }),
        ("Horodatage", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("created_at", "updated_at")

    # ── Actions ──────────────────────────────────────────────────────────────

    actions = ["mark_active", "mark_inactive"]

    @admin.action(description="Activer les clients sélectionnés")
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} client(s) activé(s).")

    @admin.action(description="Désactiver les clients sélectionnés")
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} client(s) désactivé(s).")

    # ── Colonnes calculées ───────────────────────────────────────────────────

    @admin.display(description="Total achats")
    def total_purchases_display(self, obj):
        return f"{obj.total_purchases} FCFA"

    @admin.display(description="Dette en cours")
    def outstanding_balance_display(self, obj):
        balance = obj.outstanding_balance
        if balance > 0:
            return format_html(
                '<span style="font-weight:bold; color:#c0392b;">{} FCFA</span>',
                balance,
            )
        return "—"
