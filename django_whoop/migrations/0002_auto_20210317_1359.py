# Generated by Django 3.1.7 on 2021-03-17 18:59

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whoop', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='whoopuser',
            name='whoop_createdAt',
            field=models.DateTimeField(default=datetime.datetime(1, 1, 1, 0, 0)),
        ),
        migrations.AddField(
            model_name='whoopuser',
            name='whoop_user_id',
            field=models.IntegerField(default=-1),
        ),
    ]
