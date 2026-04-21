from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class UserProfile(models.Model):

    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        EMPLOYE = "employe", "Employé"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=25, blank=True)
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.MANAGER,
    )

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"

    def __str__(self):
        return f"Profil de {self.user.username} ({self.get_role_display()})"

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_employe(self):
        return self.role == self.Role.EMPLOYE
