from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models import Sum
from decimal import Decimal

User = get_user_model()


class Sale(models.Model):

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Non payé"
        PARTIAL = "partial", "Partiel"
        PAID = "paid", "Payé"

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    sale_date = models.DateField()
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_profit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"
        ordering = ["-sale_date", "-created_at"]
        indexes = [
            models.Index(fields=["sale_date"], name="sale_date_idx"),
            models.Index(fields=["payment_status"], name="sale_payment_status_idx"),
            models.Index(fields=["client"], name="sale_client_idx"),
        ]

    def __str__(self):
        client_name = self.client.name if self.client else "Client anonyme"
        return f"Vente #{self.pk} – {client_name} – {self.sale_date}"

    # ── Paiements ─────────────────────────────────────────────────────────────

    @property
    def total_paid(self) -> Decimal:
        result = self.payments.aggregate(total=Sum("amount"))
        return result["total"] or Decimal("0.00")

    @property
    def remaining_balance(self) -> Decimal:
        return self.total_amount - self.total_paid

    # ── Mise à jour du statut et des totaux ──────────────────────────────────

    def update_payment_status(self) -> None:
        """Recalcule et sauvegarde le statut de paiement."""
        paid = self.total_paid
        if paid <= 0:
            status = self.PaymentStatus.UNPAID
        elif paid >= self.total_amount:
            status = self.PaymentStatus.PAID
        else:
            status = self.PaymentStatus.PARTIAL
        self.payment_status = status
        self.save(update_fields=["payment_status"])

    def recompute_totals(self) -> None:
        """Recalcule total_amount et total_profit depuis les SaleItems."""
        aggregates = self.items.aggregate(
            amount=Sum("line_total"),
            profit=Sum("line_profit"),
        )
        self.total_amount = aggregates["amount"] or Decimal("0.00")
        self.total_profit = aggregates["profit"] or Decimal("0.00")
        self.save(update_fields=["total_amount", "total_profit"])


class SaleItem(models.Model):
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sale_items",
    )
    service = models.ForeignKey(
        "services.Service",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sale_items",
    )
    label = models.CharField(max_length=255, blank=True, default="")
    quantity = models.PositiveIntegerField(default=1)
    # Snapshot des prix au moment de la vente
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Prix d'achat copié au moment de la vente (pour calcul du profit).",
    )
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    line_profit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = "Ligne de vente"
        verbose_name_plural = "Lignes de vente"

    def __str__(self):
        if self.product:
            name = self.product.name
        elif self.service:
            name = self.service.name
        else:
            name = self.label or "Article"
        return f"{name} × {self.quantity}"

    def clean(self):
        if not self.product and not self.service and not self.label:
            raise ValidationError("Une ligne doit référencer un produit, une prestation, ou avoir un libellé.")
        if self.product and self.service:
            raise ValidationError("Une ligne ne peut pas référencer un produit ET une prestation.")

    def save(self, *args, **kwargs):
        # Calculs automatiques avant sauvegarde
        self._snapshot_prices()
        self.line_total = self.unit_price * self.quantity
        self.line_profit = (self.unit_price - self.purchase_price_snapshot) * self.quantity
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.product:
            self.product.decrease_stock(self.quantity)

    def _snapshot_prices(self) -> None:
        """Copie les prix depuis le produit ou la prestation si non encore définis."""
        if self.product and not self.unit_price:
            self.unit_price = self.product.selling_price
            self.purchase_price_snapshot = self.product.purchase_price
        elif self.service and not self.unit_price:
            self.unit_price = self.service.price
            # Pas de prix d'achat pour un service
            self.purchase_price_snapshot = Decimal("0.00")


class Payment(models.Model):

    class Method(models.TextChoices):
        CASH = "cash", "Espèces"
        MOBILE_MONEY = "mobile_money", "Mobile Money"
        BANK = "bank", "Virement bancaire"

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="recorded_payments",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Montant encaissé en FCFA.",
    )
    payment_method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.CASH,
    )
    payment_date = models.DateField()
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ["-payment_date", "-id"]
        indexes = [
            models.Index(fields=["sale"], name="payment_sale_idx"),
            models.Index(fields=["payment_date"], name="payment_date_idx"),
        ]

    def __str__(self):
        return f"Paiement {self.amount} FCFA – Vente #{self.sale_id} – {self.payment_date}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mise à jour automatique du statut de la vente après chaque paiement
        self.sale.update_payment_status()
