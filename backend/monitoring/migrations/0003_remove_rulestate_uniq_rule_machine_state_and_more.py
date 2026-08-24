from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
        ("monitoring", "0002_alert_uniq_open_alert_customer_dedup"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="rulestate",
            name="uniq_rule_machine_state",
        ),
        migrations.AddField(
            model_name="rulestate",
            name="dimension_key",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddConstraint(
            model_name="rulestate",
            constraint=models.UniqueConstraint(
                fields=("rule", "machine", "dimension_key"),
                name="uniq_rule_machine_dimension_state",
            ),
        ),
    ]
