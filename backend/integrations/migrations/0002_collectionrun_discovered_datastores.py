from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectionrun",
            name="discovered_datastores",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
