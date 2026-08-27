import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("realtime", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RealtimeTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nonce_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="realtime_tickets", to="accounts.customer")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="realtime_tickets", to="accounts.user")),
            ],
        ),
    ]
