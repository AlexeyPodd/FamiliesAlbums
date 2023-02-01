from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Patterns
from .photos_handlers import SavingAlbumRecognitionDataToDBHandler


@receiver(post_delete, sender=Patterns)
def patterns_delete(sender, instance, **kwargs):
    instance.cluster.not_recalc_patt_del += 1
    instance.cluster.save(update_field='not_recalc_patt_del')

    # If after deletion will be left single pattern in cluster
    # (cluster should be deleted, pattern should be moved up to its parent)
    if instance.cluster.patterns_set.all().count() == 1:
        empty_cluster = instance.cluster
        last_pattern = empty_cluster.patterns_set.get()
        last_pattern.cluster = last_pattern.cluster.parent
        last_pattern.save(update_field='cluster')
        empty_cluster.delete()
    else:
        SavingAlbumRecognitionDataToDBHandler.recalculate_center(instance.cluster)
