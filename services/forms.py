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
        fields = ["name", "description", "price", "renewal_delay_days", "is_active"]
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
            "renewal_delay_days": forms.NumberInput(attrs={
                "class": _INPUT_CLASSES.replace("px-3", "pl-3 pr-16"),
                "min": "1",
                "step": "1",
                "placeholder": "Ex : 14",
            }),
        }
        help_texts = {
            "renewal_delay_days": "Laisser vide si prestation ponctuelle",
        }
        labels = {
            "name": "Nom de la prestation",
            "description": "Description",
            "price": "Prix (FCFA)",
            "renewal_delay_days": "Délai de renouvellement (jours)",
            "is_active": "Prestation active",
        }
