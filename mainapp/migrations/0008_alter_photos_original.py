# Generated by Django 4.1.3 on 2023-01-20 17:28

from django.db import migrations
import django_resized.forms
import mainapp.utils


class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0007_alter_photos_original'),
    ]

    operations = [
        migrations.AlterField(
            model_name='photos',
            name='original',
            field=django_resized.forms.ResizedImageField(crop=None, force_format='JPEG', keep_meta=False, quality=90, scale=1.0, size=[1280, 1280], upload_to=mainapp.utils.get_photo_save_path, verbose_name='Original'),
        ),
    ]
