# Generated by Django 3.1.7 on 2021-03-17 19:30

import datetime
from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('whoop', '0003_auto_20210317_1424'),
    ]

    operations = [
        migrations.AlterField(
            model_name='whoopuser',
            name='access_token_updated',
            field=models.DateTimeField(default=datetime.datetime(1, 1, 1, 0, 0, tzinfo=utc)),
        ),
        migrations.AlterField(
            model_name='whoopuser',
            name='whoop_createdAt',
            field=models.DateTimeField(default=datetime.datetime(1, 1, 1, 0, 0, tzinfo=utc)),
        ),
    ]
