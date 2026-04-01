from django import forms
from .models import Expense


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["label", "category", "amount", "expense_date", "note"]
        labels = {
            "label": "Libellé",
            "category": "Catégorie",
            "amount": "Montant (FCFA)",
            "expense_date": "Date de la dépense",
            "note": "Notes",
        }
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01", "placeholder": "0"}),
            "note": forms.Textarea(attrs={"rows": 3, "placeholder": "Détails optionnels…"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = (
            "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        )
        select_css = (
            "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-brand-500"
        )
        for field_name, field in self.fields.items():
            if field_name == "category":
                field.widget.attrs.setdefault("class", select_css)
            else:
                field.widget.attrs.setdefault("class", css)
        self.fields["label"].widget.attrs["placeholder"] = "Ex : Achat de nourriture poissons"
