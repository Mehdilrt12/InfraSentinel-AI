import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("async_tasks", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="taskrun",
            name="customer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="task_runs",
                to="accounts.customer",
            ),
        ),
        migrations.AddIndex(
            model_name="taskrun",
            index=models.Index(
                fields=["customer", "status", "started_at"],
                name="async_tasks_custome_cad816_idx",
            ),
        ),
    ]
