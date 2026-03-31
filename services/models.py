from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal


class Service(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    # Nombre de jours avant que la prestation soit à renouveler.
    # None = prestation ponctuelle, pas de rappel automatique.
    renewal_delay_days = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Délai en jours avant renouvellement. Laisser vide si ponctuel.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Prestation"
        verbose_name_plural = "Prestations"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active"], name="service_is_active_idx"),
        ]

    def __str__(self):
        return self.name

    @property
    def has_renewal(self) -> bool:
        """True si la prestation génère un rappel de renouvellement."""
        return self.renewal_delay_days is not None

    @property
    def renewal_delay_display(self) -> str:
        """Représentation lisible du délai de renouvellement."""
        if not self.has_renewal:
            return "Ponctuel"
        days = self.renewal_delay_days
        if days % 30 == 0:
            months = days // 30
            return f"Tous les {months} mois" if months > 1 else "Tous les mois"
        if days % 7 == 0:
            weeks = days // 7
            return f"Toutes les {weeks} semaines" if weeks > 1 else "Toutes les semaines"
        return f"Tous les {days} jours"


class ServiceExecution(models.Model):
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="service_executions",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="executions",
    )
    # Lien optionnel vers la ligne de vente qui a généré cette exécution
    sale_item = models.OneToOneField(
        "sales.SaleItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_execution",
    )
    execution_date = models.DateField()
    next_due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Calculée automatiquement depuis execution_date + renewal_delay_days.",
    )
    is_completed = models.BooleanField(default=False)
    reminder_sent = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Exécution de prestation"
        verbose_name_plural = "Exécutions de prestations"
        ordering = ["next_due_date"]
        indexes = [
            models.Index(fields=["next_due_date"], name="execution_next_due_idx"),
            models.Index(fields=["is_completed"], name="execution_completed_idx"),
            models.Index(fields=["client"], name="execution_client_idx"),
        ]

    def __str__(self):
        return f"{self.service.name} – {self.client.name} – {self.execution_date}"

    def save(self, *args, **kwargs):
        # Calcul automatique de next_due_date
        if self.service.has_renewal and not self.next_due_date:
            self.next_due_date = self.execution_date + timedelta(
                days=self.service.renewal_delay_days
            )
        super().save(*args, **kwargs)

    @property
    def is_overdue(self) -> bool:
        """True si la prochaine intervention est dépassée et non complétée."""
        if not self.next_due_date or self.is_completed:
            return False
        return self.next_due_date < timezone.now().date()

    @property
    def days_until_due(self) -> int | None:
        """Nombre de jours restants avant échéance (négatif si dépassé)."""
        if not self.next_due_date:
            return None
        return (self.next_due_date - timezone.now().date()).days
