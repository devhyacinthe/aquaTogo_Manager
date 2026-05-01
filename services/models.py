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


# Délai en jours selon le nombre de tours par mois
_TOURS_DELAY: dict[int, int] = {1: 30, 2: 14, 3: 10, 4: 7}

TOURS_CHOICES = [
    (1, "1 tour / mois — tous les 30 jours"),
    (2, "2 tours / mois — toutes les 2 semaines"),
    (3, "3 tours / mois — tous les 10 jours"),
    (4, "4 tours / mois — toutes les semaines"),
]


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
    # Regroupe les passages créés ensemble (multi-tours payés en une fois)
    parent_execution = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    # Lien optionnel vers la ligne de vente qui a généré cette exécution
    sale_item = models.OneToOneField(
        "sales.SaleItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_execution",
    )
    # Nombre de passages par mois choisi par le client (1, 2, 3 ou 4)
    tours_per_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=TOURS_CHOICES,
        help_text="Nombre de tours d'entretien par mois. Détermine l'intervalle entre deux passages.",
    )
    start_tour = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Numéro de ce tour dans le cycle mensuel (1-4). Null = Tour 1.",
    )
    execution_date = models.DateField()
    next_due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Calculée automatiquement depuis execution_date + intervalle selon les tours.",
    )
    is_completed = models.BooleanField(default=False)
    reminder_sent = models.BooleanField(default=False)
    confirmed = models.BooleanField(
        default=False,
        help_text="Rendez-vous confirmé par le client.",
    )
    scheduled_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Heure prévue du rendez-vous (optionnel).",
    )

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

    def interval_days(self) -> int | None:
        """Intervalle en jours entre deux passages.

        Priorité : tours_per_month (choix du client) > renewal_delay_days du service.
        """
        if self.tours_per_month:
            return _TOURS_DELAY.get(self.tours_per_month)
        if self.service.has_renewal:
            return self.service.renewal_delay_days
        return None

    def save(self, *args, **kwargs):
        if not self.next_due_date:
            days = self.interval_days()
            if days:
                raw = self.execution_date + timedelta(days=days)
                # Avance au prochain jour de semaine identique à execution_date
                offset = (self.execution_date.weekday() - raw.weekday()) % 7
                self.next_due_date = raw + timedelta(days=offset)
        super().save(*args, **kwargs)

    @property
    def is_overdue(self) -> bool:
        if not self.next_due_date or self.is_completed:
            return False
        return self.next_due_date < timezone.now().date()

    @property
    def days_until_due(self) -> int | None:
        if not self.next_due_date:
            return None
        return (self.next_due_date - timezone.now().date()).days

    @property
    def tours_display(self) -> str:
        """Affichage lisible du rythme d'entretien."""
        if not self.tours_per_month:
            return self.service.renewal_delay_display
        labels = {
            1: "1 tour/mois — tous les 30 jours",
            2: "2 tours/mois — toutes les 2 semaines",
            3: "3 tours/mois — tous les 10 jours",
            4: "4 tours/mois — toutes les semaines",
        }
        return labels[self.tours_per_month]
