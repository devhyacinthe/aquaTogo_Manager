"""
Migration de données : rattache les passages orphelins à leur passage parent.

Logique :
  Pour chaque ServiceExecution qui a un sale_item avec qty > 1
  (= plusieurs tours payés en une seule vente), on cherche les passages
  créés pour le même client + service sans sale_item, aux dates attendues
  (execution_date + i × intervalle), et on leur assigne parent_execution.
"""

from datetime import timedelta

from django.db import migrations

_TOURS_DELAY = {1: 30, 2: 15, 3: 10, 4: 7}


def backfill_parent_execution(apps, schema_editor):
    ServiceExecution = apps.get_model("services", "ServiceExecution")

    # Toutes les exécutions « tête » : liées à un sale_item avec qty > 1
    heads = (
        ServiceExecution.objects
        .filter(
            parent_execution__isnull=True,
            sale_item__isnull=False,
            sale_item__quantity__gt=1,
        )
        .select_related("sale_item", "client", "service")
    )

    for head in heads:
        qty = head.sale_item.quantity
        tours = head.tours_per_month

        if not tours or tours not in _TOURS_DELAY:
            continue

        interval = _TOURS_DELAY[tours]

        for i in range(1, qty):
            expected_date = head.execution_date + timedelta(days=interval * i)
            # Cherche un passage orphelin pour le même client + service à cette date
            orphan = (
                ServiceExecution.objects
                .filter(
                    client=head.client,
                    service=head.service,
                    execution_date=expected_date,
                    sale_item__isnull=True,
                    parent_execution__isnull=True,
                )
                .exclude(pk=head.pk)
                .first()
            )
            if orphan:
                orphan.parent_execution = head
                orphan.save(update_fields=["parent_execution"])


def reverse_backfill(apps, schema_editor):
    # Annulation : on remet parent_execution à NULL pour tout le monde
    ServiceExecution = apps.get_model("services", "ServiceExecution")
    ServiceExecution.objects.filter(
        parent_execution__isnull=False
    ).update(parent_execution=None)


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0005_add_parent_execution"),
    ]

    operations = [
        migrations.RunPython(backfill_parent_execution, reverse_code=reverse_backfill),
    ]
