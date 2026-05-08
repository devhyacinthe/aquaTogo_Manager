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


CSS = (
    "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
)


class EmployeCreateForm(forms.ModelForm):
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"class": CSS, "placeholder": "Min. 8 caractères"}),
        min_length=8,
    )
    phone = forms.CharField(
        max_length=25, required=False, label="Téléphone",
        widget=forms.TextInput(attrs={"class": CSS, "placeholder": "+228 XX XX XX XX"}),
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {"username": "Identifiant", "first_name": "Prénom",
                  "last_name": "Nom", "email": "Email"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in ("password", "phone"):
                field.widget.attrs.setdefault("class", CSS)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class EmployeEditForm(forms.ModelForm):
    phone = forms.CharField(
        max_length=25, required=False, label="Téléphone",
        widget=forms.TextInput(attrs={"class": CSS, "placeholder": "+228 XX XX XX XX"}),
    )
    new_password = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"class": CSS, "placeholder": "Laisser vide pour ne pas changer"}),
        required=False,
        min_length=8,
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        labels = {"first_name": "Prénom", "last_name": "Nom", "email": "Email"}

    def __init__(self, *args, **kwargs):
        profile = kwargs.pop("profile", None)
        super().__init__(*args, **kwargs)
        if profile:
            self.fields["phone"].initial = profile.phone
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", CSS)

    def save(self, commit=True):
        user = super().save(commit=False)
        pwd = self.cleaned_data.get("new_password")
        if pwd:
            user.set_password(pwd)
        if commit:
            user.save()
        return user


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
