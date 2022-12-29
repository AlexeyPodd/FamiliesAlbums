from django.db import models

from mainapp.models import Photos
from photoalbums.settings import AUTH_USER_MODEL


class Faces(models.Model):
    photo = models.ForeignKey(Photos, on_delete=models.CASCADE, verbose_name='Photo')
    pattern = models.ForeignKey('Patterns', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Pattern')
    loc_top = models.PositiveSmallIntegerField(verbose_name='Location Top')
    loc_right = models.PositiveSmallIntegerField(verbose_name='Location Right')
    loc_bot = models.PositiveSmallIntegerField(verbose_name='Location Bottom')
    loc_left = models.PositiveSmallIntegerField(verbose_name='Location Left')
    encoding = models.BinaryField(verbose_name='Encoding')


class Patterns(models.Model):
    person = models.ForeignKey('People', on_delete=models.CASCADE, verbose_name='Person')
    cluster = models.ForeignKey('Clusters', on_delete=models.PROTECT, verbose_name='Cluster')
    central_face = models.OneToOneField('Faces', blank=True, null=True, on_delete=models.SET_NULL, verbose_name='Central Face')
    is_registered_in_cluster = models.BooleanField(default=False, verbose_name='Is registered in cluster')


class People(models.Model):
    owner = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owner', verbose_name='Owner')
    name = models.CharField(max_length=32, verbose_name='Name')


class Clusters(models.Model):
    parent = models.ForeignKey('self', blank=True, null=True, on_delete=models.PROTECT, verbose_name='Parent')
    center = models.OneToOneField('Patterns', on_delete=models.SET(calculate_central_patttern),
                                  verbose_name='Central Face')

