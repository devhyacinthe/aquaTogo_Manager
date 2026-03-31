from django.contrib import admin
from django.utils.html import format_html
from .models import Service, ServiceExecution


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):

    # ── Liste ────────────────────────────────────────────────────────────────

    list_display = (
        "name",
        "price",
        "renewal_display",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    list_editable = ("is_active",)
    list_per_page = 30
    ordering = ("name",)

    # ── Formulaire ───────────────────────────────────────────────────────────

    fieldsets = (
        (None, {
            "fields": ("name", "description", "is_active"),
        }),
        ("Tarification", {
            "fields": ("price",),
        }),
        ("Renouvellement", {
            "fields": ("renewal_delay_days",),
            "description": "Laisser vide si la prestation est ponctuelle (pas de rappel).",
        }),
    )
    readonly_fields = ("created_at",)

    # ── Actions ──────────────────────────────────────────────────────────────

    actions = ["mark_active", "mark_inactive"]

    @admin.action(description="Activer les prestations sélectionnées")
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} prestation(s) activée(s).")

    @admin.action(description="Désactiver les prestations sélectionnées")
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} prestation(s) désactivée(s).")

    # ── Colonnes calculées ───────────────────────────────────────────────────

    @admin.display(description="Renouvellement")
    def renewal_display(self, obj):
        if not obj.has_renewal:
            return "Ponctuel"
        return format_html(
            '<span style="color:#2980b9;">{}</span>',
            obj.renewal_delay_display,
        )


@admin.register(ServiceExecution)
class ServiceExecutionAdmin(admin.ModelAdmin):

    # ── Liste ────────────────────────────────────────────────────────────────

    list_display = (
        "service",
        "client",
        "execution_date",
        "next_due_date",
        "due_status",
        "is_completed",
        "reminder_sent",
    )
    list_filter = ("is_completed", "reminder_sent", "service")
    search_fields = ("client__name", "service__name")
    list_editable = ("is_completed", "reminder_sent")
    list_per_page = 30
    date_hierarchy = "next_due_date"
    ordering = ("next_due_date",)

    # ── Formulaire ───────────────────────────────────────────────────────────

    fieldsets = (
        (None, {
            "fields": ("client", "service", "sale_item"),
        }),
        ("Dates", {
            "fields": ("execution_date", "next_due_date"),
        }),
        ("Suivi", {
            "fields": ("is_completed", "reminder_sent"),
        }),
    )
    autocomplete_fields = ("client", "service")

    # ── Colonnes calculées ───────────────────────────────────────────────────

    @admin.display(description="Échéance")
    def due_status(self, obj):
        days = obj.days_until_due
        if days is None:
            return "—"
        if obj.is_completed:
            return "Terminé"
        if days < 0:
            return format_html(
                '<span style="font-weight:bold; color:#c0392b;">En retard ({} j)</span>',
                abs(days),
            )
        if days <= 7:
            return format_html(
                '<span style="font-weight:bold; color:#e67e22;">Dans {} j</span>',
                days,
            )
        return format_html('<span style="color:#2980b9;">Dans {} j</span>', days)
