# Generated by Django 4.2 on 2023-09-18 08:40

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="pass_user",
            name="update_date",
            field=models.DateField(
                blank=True,
                db_comment="День обновления",
                default=datetime.datetime(2023, 9, 18, 15, 40, 5, 280672),
                null=True,
                verbose_name="День обновления",
            ),
        ),
    ]
