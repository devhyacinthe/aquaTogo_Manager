from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Expense(models.Model):

    class Category(models.TextChoices):
        STOCK = "stock", "Achat de stock"
        TRANSPORT = "transport", "Transport"
        EQUIPMENT = "equipment", "Matériel / Équipement"
        UTILITIES = "utilities", "Charges (eau, électricité…)"
        OTHER = "other", "Autre"

    label = models.CharField(max_length=255)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Montant de la dépense en FCFA.",
    )
    expense_date = models.DateField()
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        ordering = ["-expense_date", "-created_at"]
        indexes = [
            models.Index(fields=["expense_date"], name="expense_date_idx"),
            models.Index(fields=["category"], name="expense_category_idx"),
        ]

    def __str__(self):
        return f"{self.label} – {self.amount} FCFA ({self.expense_date})"
