from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("db_monitor", "0002_querystatsnapshot_operation_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="tablestatsnapshot",
            name="seq_tup_read",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="tablestatsnapshot",
            name="idx_tup_fetch",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="tablestatsnapshot",
            name="table_size_bytes",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="indexstatsnapshot",
            name="idx_tup_read",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="indexstatsnapshot",
            name="idx_tup_fetch",
            field=models.BigIntegerField(default=0),
        ),
    ]
