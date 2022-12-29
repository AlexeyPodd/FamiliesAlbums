# Generated by Django 4.1.3 on 2022-12-23 14:26

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django_extensions.db.fields
import mainapp.utils


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Albums',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=127, verbose_name='Title')),
                ('slug', django_extensions.db.fields.AutoSlugField(blank=True, editable=False, populate_from=['owner__username_slug', 'title'], verbose_name='URL')),
                ('date_start', models.DateField(blank=True, null=True, verbose_name='Photo date start')),
                ('date_end', models.DateField(blank=True, null=True, verbose_name='Photo date end')),
                ('location', models.CharField(blank=True, max_length=63, verbose_name='Location')),
                ('description', models.CharField(blank=True, max_length=1023, verbose_name='Description')),
                ('time_create', models.DateTimeField(auto_now_add=True, verbose_name='Date of creation')),
                ('time_update', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('is_private', models.BooleanField(default=False, verbose_name='Privacy')),
                ('in_users_favorites', models.ManyToManyField(blank=True, related_name='album_in_users_favorites', to=settings.AUTH_USER_MODEL, verbose_name="In Users' Favorites")),
            ],
            options={
                'verbose_name': 'User Album',
                'verbose_name_plural': 'Users Albums',
                'ordering': ['time_create'],
            },
        ),
        migrations.CreateModel(
            name='Photos',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=127, verbose_name='Title')),
                ('slug', django_extensions.db.fields.AutoSlugField(blank=True, editable=False, populate_from='title', unique=True, verbose_name='URL')),
                ('date_start', models.DateField(blank=True, null=True, verbose_name='Photo date start')),
                ('date_end', models.DateField(blank=True, null=True, verbose_name='Photo date end')),
                ('location', models.CharField(blank=True, max_length=63, verbose_name='Location')),
                ('description', models.CharField(blank=True, max_length=1023, verbose_name='Description')),
                ('time_create', models.DateTimeField(auto_now_add=True, verbose_name='Date of creation')),
                ('time_update', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('is_private', models.BooleanField(default=False, verbose_name='Privacy')),
                ('original', models.ImageField(upload_to=mainapp.utils.get_photo_save_path, verbose_name='Original')),
                ('album', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mainapp.albums', verbose_name='Album')),
                ('in_users_favorites', models.ManyToManyField(blank=True, related_name='photo_in_users_favorites', to=settings.AUTH_USER_MODEL, verbose_name="In Users' Favorites")),
            ],
            options={
                'verbose_name': 'User Photo',
                'verbose_name_plural': 'Users Photos',
                'ordering': ['time_create'],
            },
        ),
        migrations.AddField(
            model_name='albums',
            name='miniature',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainapp.photos', verbose_name='Miniature'),
        ),
        migrations.AddField(
            model_name='albums',
            name='owner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='owner', to=settings.AUTH_USER_MODEL, verbose_name='Owner'),
        ),
    ]
