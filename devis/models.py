from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal

User = get_user_model()


class Quote(models.Model):

    class Status(models.TextChoices):
        DRAFT     = "draft",     "Brouillon"
        SENT      = "sent",      "Envoyé"
        ACCEPTED  = "accepted",  "Accepté"
        REJECTED  = "rejected",  "Refusé"
        CONVERTED = "converted", "Converti en vente"

    client = models.ForeignKey(
        "clients.Client",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="quotes",
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    valid_until = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="quotes_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    converted_sale = models.OneToOneField(
        "sales.Sale",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="source_quote",
    )

    class Meta:
        verbose_name = "Devis"
        verbose_name_plural = "Devis"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"],     name="quote_status_idx"),
            models.Index(fields=["created_at"], name="quote_created_idx"),
        ]

    def __str__(self):
        return f"Devis #{self.pk:04d}"

    def recompute_total(self):
        self.total_amount = sum(i.line_total for i in self.items.all())
        self.save(update_fields=["total_amount"])

    @property
    def is_expired(self):
        if not self.valid_until:
            return False
        from django.utils import timezone
        return self.valid_until < timezone.now().date()


class QuoteItem(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", null=True, blank=True, on_delete=models.SET_NULL
    )
    service = models.ForeignKey(
        "services.Service", null=True, blank=True, on_delete=models.SET_NULL
    )
    label = models.CharField(max_length=255)
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Ligne de devis"
        verbose_name_plural = "Lignes de devis"

    def __str__(self):
        return f"{self.label} × {self.quantity}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity
