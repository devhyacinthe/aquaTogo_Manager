from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):

    name = models.CharField(max_length=200)
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
    )
    description = models.TextField(blank=True)
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix détail",
    )
    wholesale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        null=True,
        blank=True,
        verbose_name="Prix gros",
    )
    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True,
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ["category__name", "name"]
        indexes = [
            models.Index(fields=["is_active"], name="product_is_active_idx"),
            models.Index(fields=["name"], name="product_name_idx"),
        ]

    def __str__(self):
        return f"[{self.category.name}] {self.name}"

    @property
    def margin(self) -> Decimal:
        """Marge brute unitaire (prix vente - prix achat)."""
        return self.selling_price - self.purchase_price

    @property
    def margin_percent(self) -> Decimal:
        """Taux de marge en pourcentage par rapport au prix d'achat."""
        if self.purchase_price == 0:
            return Decimal("0.00")
        return (self.margin / self.purchase_price * 100).quantize(Decimal("0.01"))

    @property
    def is_low_stock(self) -> bool:
        """True si le stock est inférieur ou égal au seuil d'alerte."""
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self) -> bool:
        return self.stock_quantity == 0

    def decrease_stock(self, quantity: int) -> None:
        """Diminue le stock après une vente. Lève une erreur si stock insuffisant."""
        if quantity <= 0:
            raise ValueError("La quantité doit être positive.")
        if self.stock_quantity < quantity:
            raise ValueError(
                f"Stock insuffisant pour '{self.name}' "
                f"(disponible : {self.stock_quantity}, demandé : {quantity})."
            )
        self.stock_quantity -= quantity
        self.save(update_fields=["stock_quantity", "updated_at"])

    def increase_stock(self, quantity: int) -> None:
        """Augmente le stock (réapprovisionnement ou annulation de vente)."""
        if quantity <= 0:
            raise ValueError("La quantité doit être positive.")
        self.stock_quantity += quantity
        self.save(update_fields=["stock_quantity", "updated_at"])
