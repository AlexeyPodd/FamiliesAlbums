# Generated by Django 4.1.3 on 2023-01-02 16:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='photos',
            name='faces_extracted',
            field=models.BooleanField(default=False, verbose_name='Faces Extracted'),
        ),
    ]
