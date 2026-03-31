from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm

User = get_user_model()


class ProfileForm(forms.ModelForm):
    phone = forms.CharField(
        max_length=25,
        required=False,
        label="Téléphone",
        widget=forms.TextInput(attrs={"placeholder": "+228 XX XX XX XX"}),
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        labels = {
            "first_name": "Prénom",
            "last_name": "Nom",
            "email": "Adresse e-mail",
        }

    def __init__(self, *args, **kwargs):
        # Pré-remplir le champ phone depuis le profil lié
        profile = kwargs.pop("profile", None)
        super().__init__(*args, **kwargs)
        if profile:
            self.fields["phone"].initial = profile.phone
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
                "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent",
            )


class PasswordUpdateForm(DjangoPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = (
            "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        )
        self.fields["old_password"].label = "Mot de passe actuel"
        self.fields["new_password1"].label = "Nouveau mot de passe"
        self.fields["new_password2"].label = "Confirmer le nouveau mot de passe"
        for field in self.fields.values():
            field.widget.attrs["class"] = css
