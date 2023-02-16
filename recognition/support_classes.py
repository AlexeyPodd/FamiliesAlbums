import os
import pickle
import face_recognition as fr

from mainapp.models import Photos
from photoalbums.settings import MEDIA_ROOT, CLUSTER_LIMIT, MINIMAL_CLUSTER_TO_RECALCULATE, \
    UNREGISTERED_PATTERNS_CLUSTER_RELEVANT_LIMIT
from .models import Faces, Patterns, Clusters
from .utils import redis_instance


class DataDeletionSupporter:
    @classmethod
    def prepare_to_recognition(cls, album_pk):
        cls._clear_redis_album_data(album_pk, finished=False)
        cls._clear_temp_files(album_pk)
        cls._clear_db_album_data(album_pk)

    @classmethod
    def clean_after_recognition(cls, album_pk):
        cls._clear_redis_album_data(album_pk, finished=True)
        cls._clear_temp_files(album_pk)

    @staticmethod
    def _clear_redis_album_data(album_pk, finished):
        if not finished:
            redis_instance.hdel(f"album_{album_pk}", "number_of_processed_photos",
                                "number_of_verified_patterns", "people_amount")
            redis_instance.delete(f"album_{album_pk}_finished")
        else:
            redis_instance.delete(f"album_{album_pk}")
        redis_instance.delete(f"album_{album_pk}_photos")
        redis_instance.delete(*[f"photo_{photo.pk}" for photo in Photos.objects.filter(album__pk=album_pk)])

        str_patterns = (f"album_{album_pk}_pattern_", f"album_{album_pk}_person_")
        for str_pattern in str_patterns:
            i = 1
            while redis_instance.exists(str_pattern + str(i)):
                redis_instance.delete(str_pattern + str(i))
                i += 1

    @staticmethod
    def _clear_temp_files(album_pk):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{album_pk}')
        if os.path.exists(path):
            os.system(f'rm -rf {path}')

    @staticmethod
    def _clear_db_album_data(album_pk):
        for face in Faces.objects.filter(photo__album__pk=album_pk):
            Faces.objects.get(pk=face.pk).delete()


class ManageClustersSupporter:
    @classmethod
    def form_cluster_structure(cls, new_patterns_instances):
        for pattern in new_patterns_instances:
            # Root cluster and its pool
            root_cluster = Clusters.objects.get(pk=1)
            root_pool_clusters = Clusters.objects.filter(parent__pk=1).select_related('center__central_face')
            root_pool_patterns = Patterns.objects.filter(cluster__pk=1).select_related('central_face')

            pool_clusters = root_pool_clusters
            pool_patterns = root_pool_patterns
            cluster = root_cluster
            while not len(pool_clusters) + len(pool_patterns) < CLUSTER_LIMIT:
                nearest = cls._get_nearest_node(pool_clusters, pool_patterns, pattern)
                if isinstance(nearest, Clusters):
                    cluster = nearest
                    pool_clusters = Clusters.objects.filter(parent__pk=cluster.pk).select_related('center__central_face')
                    pool_patterns = Patterns.objects.filter(cluster__pk=cluster.pk).select_related('central_face')
                    continue
                elif isinstance(nearest, Patterns):
                    new_cluster = Clusters.objects.create(parent=nearest.cluster, center=nearest)
                    nearest.cluster = new_cluster
                    nearest.save()
                    pattern.cluster = new_cluster
                    pattern.save()
                    break
                else:
                    raise TypeError("Node of pool must be Clusters or Patterns type.")

            else:
                pattern.cluster = cluster
                pattern.save()

            cls.recalculate_center(cluster)

    @classmethod
    def _get_nearest_node(cls, pool_clusters, pool_patterns, pattern):
        if pool_clusters and pool_patterns:
            nearest_subcluster = cls._get_min_dist_index(pool_clusters, pattern)
            nearest_subpattern = cls._get_min_dist_index(pool_patterns, pattern)
            nearest = sorted([nearest_subcluster, nearest_subpattern], key=lambda t: t[0])[0]
        elif pool_clusters:
            nearest = cls._get_min_dist_index(pool_clusters, pattern)
        elif pool_patterns:
            nearest = cls._get_min_dist_index(pool_patterns, pattern)
        else:
            raise ValueError("Empty cluster. Check CLUSTER_LIMIT.")
        return nearest[1]

    @classmethod
    def _get_min_dist_index(cls, pool, pattern):
        compare_encodings = list(map(cls._get_node_encoding, pool))
        distances = list(fr.face_distance(compare_encodings, pickle.loads(pattern.central_face.encoding)))
        min_dist = min(distances)
        index = distances.index(min_dist)
        return min_dist, pool[index]

    @staticmethod
    def _get_node_encoding(node):
        if isinstance(node, Clusters):
            return pickle.loads(node.center.central_face.encoding)
        elif isinstance(node, Patterns):
            return pickle.loads(node.central_face.encoding)
        else:
            raise TypeError("Node of pool must be Clusters or Patterns type.")

    @staticmethod
    def _get_node_central_faces(node):
        if isinstance(node, Clusters):
            return node.center.central_face
        elif isinstance(node, Patterns):
            return node.central_face
        else:
            raise TypeError("Node of pool must be Clusters or Patterns type.")

    @classmethod
    def recalculate_center(cls, cluster, need_check_changes=True):
        """Recursive function to recalculate center of cluster.
        Recalculating all ancestors up to root cluster (including).
        Before the first iteration, the need for recalculation is checked."""
        if need_check_changes:
            cluster_len = cluster.patterns_set.count() + cluster.clusters_set.count()
            cluster_changes = cluster.patterns_set.filter(is_registered_in_cluster=False).count() +\
                              cluster.not_recalc_patt_del
        if not need_check_changes or cluster_len > MINIMAL_CLUSTER_TO_RECALCULATE and \
                cluster_changes / cluster_len >= UNREGISTERED_PATTERNS_CLUSTER_RELEVANT_LIMIT:

            subpatterns_pool = cluster.patterns_set.all()
            subclusters_pool = cluster.clusters_set.all()
            faces = list(map(cls._get_node_central_faces, subpatterns_pool)) + list(map(cls._get_node_central_faces,
                                                                                        subclusters_pool))

            min_dist_sum = center_index = None
            for i, face in enumerate(faces):
                compare_face_list = faces.copy()
                compare_face_list.remove(face)
                compare_encs = list(map(lambda f: pickle.loads(f.encoding), compare_face_list))
                distances = fr.face_distance(compare_encs, pickle.loads(face.encoding))
                dist_sum = sum(distances)
                if min_dist_sum is None or dist_sum < min_dist_sum:
                    min_dist_sum = dist_sum
                    center_index = i

            # Reset counters
            for pattern in cluster.patterns_set.filter(is_registered_in_cluster=False):
                pattern.is_registered_in_cluster = True
                pattern.save(update_fields=['is_registered_in_cluster'])
            cluster.not_recalc_patt_del = 0
            cluster.save(update_fields=['not_recalc_patt_del'])

            if center_index < len(subpatterns_pool):
                center = subpatterns_pool[center_index]
            else:
                center = subclusters_pool[center_index - len(subpatterns_pool)]

            #If center changed
            if cluster.center is None or \
                    (not isinstance(center, Patterns) or cluster.center.pk != center.pk) and cluster.pk != 1:
                cluster.center = center if isinstance(center, Patterns) else center.center
                cluster.save(update_fields=['center'])
                if cluster.parent:
                    cls.recalculate_center(cluster.parent, need_check_changes=False)

    @classmethod
    def manage_clusters_after_pattern_deletion(cls, pattern_instance):
        # --------------------------------------------------------------------------------------------------------------
        # !!! Follow checks must go in this exact order and if success - end function !!!
        # --------------------------------------------------------------------------------------------------------------
        # If it is possible to readdress cluster's pool to its parent --------------------------------------------------
        # (parent should absorb cluster's pool; cluster should be deleted)
        if pattern_instance.cluster.parent and \
                pattern_instance.cluster.parent.patterns_set.count() +\
                pattern_instance.cluster.parent.clusters_set.count() +\
                pattern_instance.cluster.patterns_set.count() +\
                pattern_instance.cluster.clusters_set.count() < CLUSTER_LIMIT:
            cls._give_pool_to_parent(pattern_instance)
            return

        # If it is possible to absorb one of the child clusters --------------------------------------------------------
        # (cluster should absorb child clusters' pool; child cluster should be deleted)
        min_pool_size, smallest_child = cls._get_smallest_child(pattern_instance)
        if min_pool_size + pattern_instance.cluster.patterns_set.count() +\
                pattern_instance.cluster.clusters_set.count() < CLUSTER_LIMIT:
            cls._absorb_child(pattern_instance, child=smallest_child)
            return

        # If after deletion will be left single pattern in cluster -----------------------------------------------------
        # (cluster should be deleted, pattern should be moved up to its parent)
        if pattern_instance.cluster.parent \
                and not pattern_instance.cluster.clusters_set.exists()\
                and pattern_instance.cluster.patterns_set.count() == 1:
            cls._move_last_pattern_up(pattern_instance)
            return

        # If it is last pattern in root cluster ------------------------------------------------------------------------
        # (pattern will be just deleted, cluster's change counter will be set 0) ---------------------------------------
        if pattern_instance.cluster.parent is None and not pattern_instance.cluster.patterns_set.exists():
            cls._delete_last_pattern(pattern_instance)
            return

        # If this is just regular deletion of pattern ------------------------------------------------------------------
        cls._simple_delete(pattern_instance)
        return
        # --------------------------------------------------------------------------------------------------------------

    @classmethod
    def _give_pool_to_parent(cls, pattern_instance):
        parent = pattern_instance.cluster.parent
        clusters = pattern_instance.cluster.clusters_set.all()
        patterns = pattern_instance.cluster.patterns_set.all()
        for cluster in clusters:
            cluster.parent = parent
        for pattern in patterns:
            pattern.cluster = parent
            pattern.is_registered_in_cluster = False
        Clusters.objects.bulk_update(clusters, fields=['parent'])
        Patterns.objects.bulk_update(patterns, fields=['cluster', 'is_registered_in_cluster'])

        # Registration of added subclusters
        parent.not_recalc_patt_del = parent.not_recalc_patt_del + len(clusters)
        parent.save(update_fields=['not_recalc_patt_del'])

        pattern_instance.cluster.delete()

        was_central_pattern = parent.center is None
        cls.recalculate_center(parent, need_check_changes=not was_central_pattern)

    @classmethod
    def _absorb_child(cls, pattern_instance, child):
        current_cluster = pattern_instance.cluster
        clusters = child.clusters_set.all()
        patterns = child.patterns_set.all()
        for cluster in clusters:
            cluster.parent = current_cluster
        for pattern in patterns:
            pattern.cluster = current_cluster
            pattern.is_registered_in_cluster = False
        Clusters.objects.bulk_update(clusters, fields=['parent'])
        Patterns.objects.bulk_update(patterns, fields=['cluster', 'is_registered_in_cluster'])

        # Registration of added subclusters
        current_cluster.not_recalc_patt_del = current_cluster.not_recalc_patt_del + len(clusters)
        current_cluster.save(update_fields=['not_recalc_patt_del'])

        child.delete()

        was_central_pattern = pattern_instance.cluster.center is None
        cls.recalculate_center(current_cluster, need_check_changes=not was_central_pattern)

    @classmethod
    def _get_smallest_child(cls, pattern_instance):
        current_cluster = pattern_instance.cluster
        children_clusters = current_cluster.clusters_set.all()
        min_pool_size = CLUSTER_LIMIT
        smallest_index = 0
        for i, cluster in enumerate(children_clusters):
            pool_size = cluster.patterns_set.count() + cluster.clusters_set.count()
            if pool_size < min_pool_size:
                min_pool_size = pool_size
                smallest_index = i

        smallest_child = children_clusters[smallest_index] if children_clusters else None

        return min_pool_size, smallest_child

    @classmethod
    def _move_last_pattern_up(cls, pattern_instance):
        parent = pattern_instance.cluster.parent
        current_cluster = pattern_instance.cluster
        last_pattern = current_cluster.patterns_set.get()

        last_pattern.cluster = parent
        last_pattern.is_registered_in_cluster = False
        last_pattern.save(update_fields=['cluster', 'is_registered_in_cluster'])

        current_cluster.delete()

        was_central_pattern = parent.center is None
        cls.recalculate_center(parent, need_check_changes=not was_central_pattern)

    @classmethod
    def _delete_last_pattern(cls, pattern_instance):
        root = pattern_instance.cluster
        root.not_recalc_patt_del = 0
        root.save(update_fields=['not_recalc_patt_del'])
        return

    @classmethod
    def _simple_delete(cls, pattern_instance):
        cluster = pattern_instance.cluster
        cluster.not_recalc_patt_del = cluster.not_recalc_patt_del + 1
        cluster.save(update_fields=['not_recalc_patt_del'])

        was_central_pattern = pattern_instance.cluster.center is None
        cls.recalculate_center(pattern_instance.cluster, need_check_changes=not was_central_pattern)
