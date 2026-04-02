from django import forms
from .models import Product, ProductCategory

_INPUT_CLASSES = (
    "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
)


class ProductCategoryForm(forms.ModelForm):
    class Meta:
        model = ProductCategory
        fields = ["name", "slug"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT_CLASSES, "placeholder": "Ex : Reptile"}),
            "slug": forms.TextInput(attrs={"class": _INPUT_CLASSES, "placeholder": "Ex : reptile"}),
        }
        labels = {"name": "Nom de la catégorie", "slug": "Identifiant (slug, unique)"}
        help_texts = {"slug": "Lettres minuscules et tirets uniquement. Ex : aquarium-marin"}


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "category",
            "description",
            "purchase_price",
            "selling_price",
            "stock_quantity",
            "low_stock_threshold",
            "image",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = _INPUT_CLASSES
        for field_name, field in self.fields.items():
            if field_name not in ("image", "is_active", "category"):
                field.widget.attrs.setdefault("class", css)
        self.fields["category"].widget.attrs["class"] = (
            "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-brand-500"
        )
        self.fields["category"].empty_label = "Choisir une catégorie"
        self.fields["description"].widget.attrs["rows"] = 3
        self.fields["image"].widget.attrs["accept"] = "image/*"
        self.fields["purchase_price"].widget.attrs["placeholder"] = "0"
        self.fields["selling_price"].widget.attrs["placeholder"] = "0"
        self.fields["stock_quantity"].widget.attrs["min"] = "0"
        self.fields["low_stock_threshold"].widget.attrs["min"] = "0"
