from django.db import migrations, models
import django.db.models.deletion


def migrate_categories(apps, schema_editor):
    ProductCategory = apps.get_model("products", "ProductCategory")
    Product = apps.get_model("products", "Product")
    fish = ProductCategory.objects.create(name="Poisson", slug="fish")
    accessory = ProductCategory.objects.create(name="Accessoire", slug="accessory")
    aquarium = ProductCategory.objects.create(name="Aquarium", slug="aquarium")
    mapping = {"fish": fish, "accessory": accessory, "aquarium": aquarium}
    for p in Product.objects.all():
        p.category_fk = mapping.get(p.category, accessory)
        p.save(update_fields=["category_fk"])


def reverse_migrate_categories(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    for p in Product.objects.select_related("category_fk").all():
        if p.category_fk:
            p.category = p.category_fk.slug
            p.save(update_fields=["category"])


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0003_add_aquarium_category"),
    ]

    operations = [
        # 1. Créer le modèle ProductCategory
        migrations.CreateModel(
            name="ProductCategory",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("slug", models.SlugField(unique=True)),
            ],
            options={
                "verbose_name": "Catégorie",
                "verbose_name_plural": "Catégories",
                "ordering": ["name"],
            },
        ),
        # 2. Ajouter FK nullable sur Product
        migrations.AddField(
            model_name="product",
            name="category_fk",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="products.productcategory",
            ),
        ),
        # 3. RunPython pour migrer les données
        migrations.RunPython(migrate_categories, reverse_migrate_categories),
        # 4. Rendre le FK non-null
        migrations.AlterField(
            model_name="product",
            name="category_fk",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="products.productcategory",
            ),
        ),
        # 5. Supprimer l'index nommé sur l'ancien champ category
        migrations.RemoveIndex(
            model_name="product",
            name="product_category_idx",
        ),
        # 6. Supprimer l'ancien champ category CharField
        migrations.RemoveField(
            model_name="product",
            name="category",
        ),
        # 7. Renommer category_fk -> category
        migrations.RenameField(
            model_name="product",
            old_name="category_fk",
            new_name="category",
        ),
    ]
