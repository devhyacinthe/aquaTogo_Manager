from django import forms
from .models import Client

_INPUT_CLASSES = (
    "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
)

_TEXTAREA_CLASSES = (
    "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-none"
)


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "phone", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": _INPUT_CLASSES,
                "placeholder": "Nom complet du client",
            }),
            "phone": forms.TextInput(attrs={
                "class": _INPUT_CLASSES,
                "placeholder": "+228 XX XX XX XX",
                "type": "tel",
            }),
            "notes": forms.Textarea(attrs={
                "class": _TEXTAREA_CLASSES,
                "rows": 3,
                "placeholder": "Préférences, localisation, informations utiles…",
            }),
        }
        labels = {
            "name": "Nom du client",
            "phone": "Téléphone",
            "notes": "Notes",
        }
