from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0002_serviceexecution"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceexecution",
            name="confirmed",
            field=models.BooleanField(
                default=False,
                help_text="Rendez-vous confirmé par le client.",
            ),
        ),
        migrations.AddField(
            model_name="serviceexecution",
            name="scheduled_time",
            field=models.TimeField(
                blank=True,
                null=True,
                help_text="Heure prévue du rendez-vous (optionnel).",
            ),
        ),
    ]
