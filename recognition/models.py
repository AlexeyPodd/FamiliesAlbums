from django.db import models
from django_extensions.db.fields import AutoSlugField

from mainapp.models import Photos
from photoalbums.settings import AUTH_USER_MODEL


class Faces(models.Model):
    """Model representing the face.
     Contains a link to the photo, coordinates of the location of the face on it
      and encoding of the face for recognition."""

    photo = models.ForeignKey(Photos, on_delete=models.CASCADE, verbose_name='Photo')
    index = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Index on photo')
    slug = AutoSlugField(populate_from=['photo__slug', 'index'], unique=True, db_index=True, verbose_name='Face URL')
    pattern = models.ForeignKey('Patterns', on_delete=models.CASCADE, null=True, blank=True, verbose_name='Pattern')
    loc_top = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Location Top')
    loc_right = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Location Right')
    loc_bot = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Location Bottom')
    loc_left = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Location Left')
    encoding = models.BinaryField(null=True, blank=True, verbose_name='Encoding')

    def __str__(self):
        return f"{self.photo}__(top={self.loc_top};left={self.loc_left})"

    class Meta:
        verbose_name = 'Recognized Face'
        verbose_name_plural = 'Recognized Faces'
        ordering = ['photo', 'index']


class Patterns(models.Model):
    """Model that contains faces of the same person in different photos
     that are similar enough for automatic recognition."""

    person = models.ForeignKey('People', blank=True, null=True, on_delete=models.CASCADE, verbose_name='Person')
    cluster = models.ForeignKey('Clusters', blank=True, null=True, on_delete=models.PROTECT, verbose_name='Cluster')
    central_face = models.OneToOneField('Faces', blank=True, null=True, on_delete=models.SET_NULL,
                                        verbose_name='Central Face')
    is_registered_in_cluster = models.BooleanField(default=False, verbose_name='Is registered in cluster')

    class Meta:
        verbose_name = 'Face Pattern'
        verbose_name_plural = 'Faces Patterns'
        ordering = ['person', 'central_face']


class People(models.Model):
    """Model contains different facial patterns of one person."""

    owner = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user', verbose_name='User')
    name = models.CharField(max_length=100, verbose_name='Name')
    slug = AutoSlugField(populate_from='name', db_index=True, unique=True, verbose_name='Face URL')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Recognized Person'
        verbose_name_plural = 'Recognized People'
        ordering = ['owner', 'name']


class Clusters(models.Model):
    """Module that unites the most similar patterns into groups
     to simplify searching people by encoding of their faces (patterns).
     Fractal structure is used."""

    parent = models.ForeignKey('self', blank=True, null=True, on_delete=models.PROTECT, verbose_name='Parent')
    center = models.ForeignKey('Patterns', blank=True, null=True, on_delete=models.SET_NULL,
                               verbose_name='Central Pattern')
    not_recalc_patt_del = models.PositiveSmallIntegerField(default=0,
                                                           verbose_name='Not recalculated patterns deletions')

    class Meta:
        verbose_name = 'Fractal Cluster of Patterns'
        verbose_name_plural = 'Fractal Clusters of Patterns'
        ordering = ['-parent']
