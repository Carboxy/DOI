# Generated by Django 3.0.7 on 2020-08-10 23:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('v0', '0003_auto_20200807_1716'),
    ]

    operations = [
        migrations.AddField(
            model_name='masks',
            name='height',
            field=models.IntegerField(default=5000),
        ),
        migrations.AddField(
            model_name='masks',
            name='width',
            field=models.IntegerField(default=3000),
        ),
    ]
