from django.db import models
from django.core.validators import RegexValidator
from decimal import Decimal


phone_validator = RegexValidator(
    regex=r"^\+?[\d\s\-]{7,20}$",
    message="Numéro de téléphone invalide.",
)


class Client(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(
        max_length=25,
        validators=[phone_validator],
        blank=True,
    )
    notes = models.TextField(
        blank=True,
        help_text="Informations utiles : préférences, localisation, contexte.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="client_name_idx"),
            models.Index(fields=["is_active"], name="client_is_active_idx"),
        ]

    def __str__(self):
        return self.name

    # ── Historique des ventes ─────────────────────────────────────────────────

    @property
    def total_purchases(self) -> Decimal:
        """Montant total facturé à ce client (toutes ventes confondues)."""
        result = self.sales.aggregate(total=models.Sum("total_amount"))
        return result["total"] or Decimal("0.00")

    @property
    def total_paid(self) -> Decimal:
        """Montant total effectivement encaissé sur toutes ses ventes."""
        from django.db.models import Sum
        result = self.sales.aggregate(
            total=Sum("payments__amount")
        )
        return result["total"] or Decimal("0.00")

    @property
    def outstanding_balance(self) -> Decimal:
        """Dette totale en cours (montant facturé – montant payé)."""
        return self.total_purchases - self.total_paid

    @property
    def has_debt(self) -> bool:
        return self.outstanding_balance > Decimal("0.00")

    # ── Rappels de prestation ─────────────────────────────────────────────────

    def upcoming_service_executions(self, days: int = 30):
        """Retourne les exécutions de service dues aujourd'hui ou dans les N prochains jours."""
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.now().date()
        limit = today + timedelta(days=days)
        return self.service_executions.filter(
            is_completed=False,
            next_due_date__gte=today,
            next_due_date__lte=limit,
        ).select_related("service").order_by("next_due_date")
