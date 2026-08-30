from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("monitoring", "0005_audit_log_append_only")]

    operations = [
        migrations.AddField(
            model_name="rulestate",
            name="consecutive_matches",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="rulestate",
            name="consecutive_normal",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="rulestate",
            name="last_matching_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
