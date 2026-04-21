from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model

from .models import UserProfile

User = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 0
    fields = ("phone", "role")


class CustomUserAdmin(UserAdmin):
    inlines = [UserProfileInline]
    list_display = ("username", "email", "first_name", "last_name", "get_role", "is_staff")

    @admin.display(description="Rôle")
    def get_role(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.get_role_display() if profile else "—"

    def save_formset(self, request, form, formset, change):
        if formset.model is UserProfile:
            instances = formset.save(commit=False)
            for instance in instances:
                UserProfile.objects.update_or_create(
                    user=instance.user,
                    defaults={"phone": instance.phone, "role": instance.role},
                )
            formset.save_m2m()
        else:
            super().save_formset(request, form, formset, change)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
