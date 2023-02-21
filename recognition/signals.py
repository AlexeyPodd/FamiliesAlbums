from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Faces, Patterns, People
from .supporters import ManageClustersSupporter
from .utils import recalculate_pattern_center


@receiver(post_delete, sender=Faces)
def faces_delete(sender, instance, **kwargs):
    """Deletion empty patterns or recalculating its center"""

    try:
        pattern = instance.pattern
    except Patterns.DoesNotExist:
        pattern = None
    if pattern:
        if not pattern.faces_set.exists():
            instance.pattern.delete()
        else:
            recalculate_pattern_center(pattern=pattern)


@receiver(post_delete, sender=Patterns)
def patterns_delete(sender, instance, **kwargs):
    # If pattern's person empty now - deleting it
    try:
        person = instance.person
    except People.DoesNotExist:
        person = None
    if person and not person.patterns_set.exists():
        instance.person.delete()

    ManageClustersSupporter.manage_clusters_after_pattern_deletion(instance)
