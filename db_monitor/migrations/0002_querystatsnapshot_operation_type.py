from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("db_monitor", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="querystatsnapshot",
            name="operation_type",
            field=models.CharField(
                choices=[
                    ("SELECT", "SELECT"),
                    ("INSERT", "INSERT"),
                    ("UPDATE", "UPDATE"),
                    ("DELETE", "DELETE"),
                    ("OTHER", "Other"),
                    ("UNKNOWN", "Unknown"),
                ],
                default="UNKNOWN",
                max_length=20,
            ),
        ),
    ]
