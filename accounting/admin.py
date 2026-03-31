from django.contrib import admin
from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):

    # ── Liste ────────────────────────────────────────────────────────────────

    list_display = (
        "label",
        "category",
        "amount_display",
        "expense_date",
    )
    list_filter = ("category", "expense_date")
    search_fields = ("label", "note")
    list_per_page = 30
    date_hierarchy = "expense_date"
    ordering = ("-expense_date",)

    # ── Formulaire ───────────────────────────────────────────────────────────

    fieldsets = (
        (None, {
            "fields": ("label", "category", "expense_date"),
        }),
        ("Montant", {
            "fields": ("amount",),
        }),
        ("Note", {
            "fields": ("note",),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("created_at",)

    # ── Colonnes calculées ───────────────────────────────────────────────────

    @admin.display(description="Montant")
    def amount_display(self, obj):
        return f"{obj.amount} FCFA"
