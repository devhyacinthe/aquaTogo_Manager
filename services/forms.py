from django import forms
from .models import Service

_INPUT_CLASSES = (
    "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
)

_TEXTAREA_CLASSES = (
    "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-none"
)


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ["name", "description", "price", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": _INPUT_CLASSES,
                "placeholder": "Ex : Nettoyage aquarium",
            }),
            "description": forms.Textarea(attrs={
                "class": _TEXTAREA_CLASSES,
                "rows": 3,
                "placeholder": "Description de la prestation (optionnel)…",
            }),
            "price": forms.NumberInput(attrs={
                "class": _INPUT_CLASSES.replace("px-3", "pl-3 pr-16"),
                "min": "0",
                "step": "1",
                "placeholder": "0",
            }),
        }
        labels = {
            "name": "Nom de la prestation",
            "description": "Description",
            "price": "Prix (FCFA)",
            "is_active": "Prestation active",
        }
