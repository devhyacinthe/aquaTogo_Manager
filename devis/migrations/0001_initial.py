from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clients", "0001_initial"),
        ("products", "0001_initial"),
        ("services", "0001_initial"),
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Quote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(
                    choices=[
                        ("draft",     "Brouillon"),
                        ("sent",      "Envoyé"),
                        ("accepted",  "Accepté"),
                        ("rejected",  "Refusé"),
                        ("converted", "Converti en vente"),
                    ],
                    default="draft",
                    max_length=15,
                )),
                ("valid_until", models.DateField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("total_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("client", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="quotes",
                    to="clients.client",
                )),
                ("created_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="quotes_created",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("converted_sale", models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="source_quote",
                    to="sales.sale",
                )),
            ],
            options={
                "verbose_name": "Devis",
                "verbose_name_plural": "Devis",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="QuoteItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=255)),
                ("unit_price", models.DecimalField(
                    decimal_places=2,
                    max_digits=12,
                    validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                )),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("quote", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="items",
                    to="devis.quote",
                )),
                ("product", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to="products.product",
                )),
                ("service", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to="services.service",
                )),
            ],
            options={
                "verbose_name": "Ligne de devis",
                "verbose_name_plural": "Lignes de devis",
            },
        ),
        migrations.AddIndex(
            model_name="quote",
            index=models.Index(fields=["status"],     name="quote_status_idx"),
        ),
        migrations.AddIndex(
            model_name="quote",
            index=models.Index(fields=["created_at"], name="quote_created_idx"),
        ),
    ]
