# Generated by Django 3.1.7 on 2021-03-18 18:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whoop', '0005_daily_recovery_sleep_sleepdetail_strain_workout'),
    ]

    operations = [
        migrations.AddField(
            model_name='workout',
            name='averageHeartRate',
            field=models.FloatField(null=True),
        ),
        migrations.AddField(
            model_name='workout',
            name='cumulativeWorkoutStrain',
            field=models.FloatField(null=True),
        ),
        migrations.AddField(
            model_name='workout',
            name='during_lower',
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name='workout',
            name='during_upper',
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name='workout',
            name='kilojoules',
            field=models.FloatField(null=True),
        ),
        migrations.AddField(
            model_name='workout',
            name='maxHeartRate',
            field=models.FloatField(null=True),
        ),
        migrations.AddField(
            model_name='workout',
            name='rawScore',
            field=models.FloatField(null=True),
        ),
        migrations.AddField(
            model_name='workout',
            name='score',
            field=models.FloatField(null=True),
        ),
        migrations.AddField(
            model_name='workout',
            name='sportId',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='workout',
            name='id',
            field=models.IntegerField(primary_key=True, serialize=False),
        ),
    ]