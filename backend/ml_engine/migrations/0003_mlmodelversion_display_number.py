from django.db import migrations, models


def assign_display_numbers(apps, _schema_editor):
    model = apps.get_model("ml_engine", "MLModelVersion")
    customer_ids = model.objects.order_by().values_list(
        "customer_id", flat=True
    ).distinct()
    for customer_id in customer_ids.iterator():
        ordered_ids = model.objects.filter(customer_id=customer_id).order_by(
            "created_at", "pk"
        ).values_list("pk", flat=True)
        for display_number, model_id in enumerate(ordered_ids.iterator(), start=1):
            model.objects.filter(pk=model_id).update(display_number=display_number)


def clear_display_numbers(apps, _schema_editor):
    apps.get_model("ml_engine", "MLModelVersion").objects.update(
        display_number=None
    )


class Migration(migrations.Migration):
    dependencies = [
        ("ml_engine", "0002_mlmodelversion_uniq_active_ml_model_customer"),
    ]

    operations = [
        migrations.AddField(
            model_name="mlmodelversion",
            name="display_number",
            field=models.PositiveBigIntegerField(editable=False, null=True),
        ),
        migrations.RunPython(assign_display_numbers, clear_display_numbers),
        migrations.AlterField(
            model_name="mlmodelversion",
            name="display_number",
            field=models.PositiveBigIntegerField(editable=False),
        ),
        migrations.AddConstraint(
            model_name="mlmodelversion",
            constraint=models.UniqueConstraint(
                fields=("customer", "display_number"),
                name="uniq_ml_customer_display_number",
            ),
        ),
    ]
