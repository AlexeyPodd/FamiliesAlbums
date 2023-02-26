import os
import pickle
import re
from typing import List

import face_recognition as fr
from django.http import Http404

from mainapp.models import Photos
from photoalbums.settings import MEDIA_ROOT, CLUSTER_LIMIT, MINIMAL_CLUSTER_TO_RECALCULATE, \
    UNREGISTERED_PATTERNS_CLUSTER_RELEVANT_LIMIT, REDIS_DATA_EXPIRATION_SECONDS
from .data_classes import FaceData, PatternData
from .models import Faces, Patterns, Clusters
from .utils import redis_instance, redis_instance_raw


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
        pks = [photo.pk for photo in Photos.objects.filter(album__pk=album_pk)]
        RedisSupporter.clear_redis_album_data(album_pk, finished=finished, photo_pks=pks)

    @staticmethod
    def _clear_temp_files(album_pk):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{album_pk}')
        if os.path.exists(path):
            os.system(f'rm -rf {path}')

    @staticmethod
    def _clear_db_album_data(album_pk):
        for face in Faces.objects.filter(photo__album__pk=album_pk):
            Faces.objects.get(pk=face.pk).delete()


class RedisSupporter:
    @staticmethod
    def set_stage_and_status(album_pk: int, stage: int, status: str):
        redis_instance.hset(f"album_{album_pk}", "current_stage", stage)
        redis_instance.hset(f"album_{album_pk}", "status", status)
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_stage(album_pk: int):
        return int(redis_instance.hget(f"album_{album_pk}", "current_stage"))

    @classmethod
    def get_stage_or_404(cls, album_pk: int):
        try:
            return cls.get_stage(album_pk)
        except TypeError:
            raise Http404

    @staticmethod
    def get_status(album_pk: int):
        return redis_instance.hget(f"album_{album_pk}", "status")

    @classmethod
    def get_status_or_completed(cls, album_pk: int):
        if redis_instance.hexists(f"album_{album_pk}", "current_stage"):
            return cls.get_status(album_pk)
        else:
            return 'completed'

    @staticmethod
    def set_no_faces(album_pk: int):
        redis_instance.set(f"album_{album_pk}_finished", "no_faces")
        redis_instance.expire(f"album_{album_pk}_finished", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_processed_photos_amount(album_pk: int):
        try:
            return int(redis_instance.hget(f"album_{album_pk}", "number_of_processed_photos"))
        except TypeError:
            return 0

    @staticmethod
    def get_face_locations_in_photo(photo_pk: int):
        faces_locations = []
        i = 1
        while redis_instance.hexists(f"photo_{photo_pk}", f"face_{i}_location"):
            faces_locations.append(pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{i}_location")))
            i += 1
        return faces_locations

    @staticmethod
    def register_photo_processed(album_pk: int):
        redis_instance.hincrby(f"album_{album_pk}", "number_of_processed_photos")
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def reset_processed_photos_amount(album_pk: int):
        redis_instance.hset(f"album_{album_pk}", "number_of_processed_photos", 0)
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_first_photo_slug(album_pk: int):
        return redis_instance.lindex(f"album_{album_pk}_photos", 0)

    @staticmethod
    def get_last_photo_slug(album_pk: int):
        return redis_instance.lindex(f"album_{album_pk}_photos", -1)

    @staticmethod
    def get_next_photo_slug(album_pk: int, current_photo_slug: str):
        return redis_instance.lindex(f"album_{album_pk}_photos",
                                     redis_instance.lpos(f"album_{album_pk}_photos", current_photo_slug) + 1)

    @staticmethod
    def get_photo_slugs_amount(album_pk: int):
        return redis_instance.llen(f"album_{album_pk}_photos")

    @staticmethod
    def photo_processed_and_no_faces_found(photo_pk: int):
        if not redis_instance.exists(f"photo_{photo_pk}"):
            return False
        elif redis_instance.hexists(f"photo_{photo_pk}", "face_1_location"):
            return False
        else:
            return True

    @staticmethod
    def photo_processed_and_some_faces_found(photo_pk: int):
        if not redis_instance.exists(f"photo_{photo_pk}"):
            return False
        elif redis_instance.hexists(f"photo_{photo_pk}", "face_1_location"):
            return True
        else:
            return False

    @classmethod
    def renumber_faces_of_photo(cls, photo_pk):
        faces_amount = cls.get_faces_amount_in_photo(photo_pk)
        count = 0
        for i in range(1, faces_amount + 1):
            if cls.is_face_in_photo(photo_pk, i):
                count += 1
                if count != i:
                    redis_instance.hset(f"photo_{photo_pk}",
                                        f"face_{count}_location",
                                        redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{i}_location"))
                    redis_instance.hdel(f"photo_{photo_pk}", f"face_{i}_location")
                    redis_instance.hset(f"photo_{photo_pk}",
                                        f"face_{count}_encoding",
                                        redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{i}_encoding"))
                    redis_instance.hdel(f"photo_{photo_pk}", f"face_{i}_encoding")

        redis_instance.hset(f"photo_{photo_pk}", "faces_amount", count)
        redis_instance.expire(f"photo_{photo_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_faces_amount_in_photo(photo_pk: int):
        return int(redis_instance.hget(f"photo_{photo_pk}", "faces_amount"))

    @staticmethod
    def del_face(photo_pk: int, face_name: str):
        redis_instance.hdel(f"photo_{photo_pk}", face_name + "_location", face_name + "_encoding")
        redis_instance.expire(f"photo_{photo_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def is_face_in_photo(photo_pk: int, face_index: int):
        return redis_instance.hexists(f"photo_{photo_pk}", f"face_{face_index}_location")

    @staticmethod
    def is_face_in_pattern(album_pk: int, face_index: int, pattern_index: int):
        return redis_instance.hexists(f"album_{album_pk}_pattern_{pattern_index}", f"face_{face_index}")

    @classmethod
    def get_album_faces_amounts(cls, album_pk: int):
        amounts = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_pattern_{i}"):
            amounts.append(cls.get_pattern_faces_amount(album_pk, i))
            i += 1
        return tuple(amounts)

    @staticmethod
    def get_pattern_faces_amount(album_pk: int, pattern_index: int):
        try:
            return int(redis_instance.hget(f"album_{album_pk}_pattern_{pattern_index}", "faces_amount"))
        except TypeError:
            return 0

    @staticmethod
    def set_pattern_faces_amount(album_pk: int, pattern_index: int, faces_amount: int):
        redis_instance.hset(f"album_{album_pk}_pattern_{pattern_index}", "faces_amount", faces_amount)

    @staticmethod
    def get_verified_patterns_amount(album_pk: int):
        try:
            return int(redis_instance.hget(f"album_{album_pk}", "number_of_verified_patterns"))
        except TypeError:
            return 0

    @staticmethod
    def move_face_data(album_pk: int, face_name: str, from_pattern: int, to_pattern: int):
        face_data = redis_instance.hget(f"album_{album_pk}_pattern_{from_pattern}", face_name)
        redis_instance.hset(f"album_{album_pk}_pattern_{to_pattern}",
                            face_name,
                            face_data)
        redis_instance.hdel(f"album_{album_pk}_pattern_{from_pattern}", face_name)
        redis_instance.expire(f"album_{album_pk}_pattern_{to_pattern}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{album_pk}_pattern_{from_pattern}", REDIS_DATA_EXPIRATION_SECONDS)

    @classmethod
    def renumber_faces_in_patterns(cls, album_pk: int, pattern_index: int, faces_amount: int):
        count = 0
        for j in range(1, faces_amount + 1):
            if cls.is_face_in_pattern(album_pk, face_index=j, pattern_index=pattern_index):
                count += 1
                if count != j:
                    # Renumbering data keys in redis
                    redis_instance.hset(f"album_{album_pk}_pattern_{pattern_index}",
                                        f"face_{count}",
                                        redis_instance.hget(f"album_{album_pk}_pattern_{pattern_index}",
                                                            f"face_{j}"))
                    redis_instance.hdel(f"album_{album_pk}_pattern_{pattern_index}", f"face_{j}")

        redis_instance.hset(f"album_{album_pk}_pattern_{pattern_index}", "faces_amount", count)
        redis_instance.expire(f"album_{album_pk}_pattern_{pattern_index}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def recalculate_pattern_center(album_pk: int, pattern_index: int):
        # Get data from redis
        for i in range(1, int(redis_instance.hget(f"album_{album_pk}_pattern_{pattern_index}",
                                                  "faces_amount")) + 1):
            face_address = redis_instance.hget(f"album_{album_pk}_pattern_{pattern_index}", f"face_{i}")
            photo_pk, face_ind = re.search(r'photo_(\d+)_face_(\d+)', face_address).groups()
            face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_location"))
            face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_encoding"))
            face = FaceData(photo_pk=int(photo_pk),
                            index=int(face_ind),
                            location=face_loc,
                            encoding=face_enc)
            if i == 1:
                pattern = PatternData(face)
            else:
                pattern.add_face(face)

        # Calculate center of pattern
        pattern.find_central_face()

        # Set central face to redis
        for i, face in enumerate(pattern, 1):
            if face is pattern.central_face:
                redis_instance.hset(f"album_{album_pk}_pattern_{pattern_index}", "central_face", f"face_{i}")
                redis_instance.expire(f"album_{album_pk}_pattern_{pattern_index}", REDIS_DATA_EXPIRATION_SECONDS)
                break

    @staticmethod
    def set_single_face_central(album_pk: int, total_patterns_amount: int, skip: int):
        for i in range(skip + 1, total_patterns_amount + 1):
            redis_instance.hset(f"album_{album_pk}_pattern_{i}", "central_face", "face_1")
            redis_instance.expire(f"album_{album_pk}_pattern_{i}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def register_verified_patterns(album_pk: int, amount: int):
        redis_instance.hset(f"album_{album_pk}", "number_of_verified_patterns", amount)
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_indexes_of_single_patterns(album_pk):
        single_patterns = []
        for x in range(1, int(redis_instance.hget(f"album_{album_pk}", "number_of_verified_patterns")) + 1):
            if not redis_instance.hexists(f"album_{album_pk}_pattern_{x}", "person"):
                single_patterns.append(x)
        return tuple(single_patterns)

    @staticmethod
    def encrease_and_get_people_amount(album_pk: int):
        redis_instance.hincrby(f"album_{album_pk}", "people_amount")
        return redis_instance.hget(f"album_{album_pk}", "people_amount")

    @staticmethod
    def check_any_tech_matches(album_pk: int):
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{album_pk}_person_{i}", "tech_pair"):
                return True
            i += 1
        else:
            return False

    @staticmethod
    def get_matching_people(album_pk: int):
        old_people_pks = []
        new_people_inds = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{album_pk}_person_{i}", "tech_pair"):
                pk = int(redis_instance.hget(f"album_{album_pk}_person_{i}", "tech_pair")[7:])
                old_people_pks.append(pk)
                new_people_inds.append(i)
            i += 1

        return old_people_pks, new_people_inds

    @staticmethod
    def get_first_patterns_indexes_of_people(album_pk: int, people_indexes: List[int]):
        return [redis_instance.hget(f"album_{album_pk}_person_{x}", "pattern_1") for x in people_indexes]

    @staticmethod
    def check_existing_new_single_people(album_pk: int):
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if not redis_instance.hexists(f"album_{album_pk}_person_{i}", "real_pair"):
                return True
            i += 1
        else:
            return False

    @staticmethod
    def get_old_paired_people(album_pk: int):
        paired = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{album_pk}_person_{i}", "real_pair"):
                paired.append(int(redis_instance.hget(f"album_{album_pk}_person_{i}", "real_pair")[7:]))
            i += 1
        return paired

    @staticmethod
    def set_verified_pair(album_pk: int, new_per_ind, old_per_pk):
        redis_instance.hset(f"album_{album_pk}_person_{new_per_ind}", "real_pair", f"person_{old_per_pk}")

    @staticmethod
    def get_new_unpaired_people(album_pk: int):
        new_people_inds = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if not redis_instance.hexists(f"album_{album_pk}_person_{i}", "real_pair"):
                new_people_inds.append(i)
            i += 1

        patt_inds = [redis_instance.hget(f"album_{album_pk}_person_{x}", "pattern_1") for x in new_people_inds]
        face_urls = [f"/media/temp_photos/album_{album_pk}/patterns/{x}/1.jpg" for x in patt_inds]

        return tuple(zip(new_people_inds, face_urls))

    @staticmethod
    def get_old_paired_people_pks(album_pk: int):
        paired = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{album_pk}_person_{i}", "real_pair"):
                paired.append(int(redis_instance.hget(f"album_{album_pk}_person_{i}", "real_pair")[7:]))
            i += 1
        return paired

    @staticmethod
    def set_new_pair(album_pk: int, new_person_ind: int, old_person_pk: int):
        redis_instance.hset(f'album_{album_pk}_person_{new_person_ind}', 'real_pair', f'person_{old_person_pk}')
        redis_instance.expire(f'album_{album_pk}_person_{new_person_ind}', REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_finished_status(album_pk: int):
        return redis_instance.get(f"album_{album_pk}_finished")

    @staticmethod
    def set_pattern_to_person(album_pk: int, pattern_name: str,
                              pattern_number_in_person: (int, str), person_number: (int, str)):
        redis_instance.hset(f"album_{album_pk}_{pattern_name}", "person", person_number)
        redis_instance.expire(f"album_{album_pk}_{pattern_name}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.hset(f"album_{album_pk}_person_{person_number}",
                            f"pattern_{pattern_number_in_person}", pattern_name[8:])
        redis_instance.expire(f"album_{album_pk}_person_{person_number}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def set_created_person(album_pk: int, pattern_name: str):
        redis_instance.hincrby(f"album_{album_pk}", "people_amount")
        new_person_number = redis_instance.hget(f"album_{album_pk}", "people_amount")

        redis_instance.hset(f"album_{album_pk}_{pattern_name}", "person", new_person_number)
        redis_instance.hset(f"album_{album_pk}_person_{new_person_number}",
                            f"pattern_1", pattern_name[8:])
        redis_instance.expire(f"album_{album_pk}_{pattern_name}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{album_pk}_person_{new_person_number}",
                              REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def clear_redis_album_data(album_pk: int, finished: bool, photo_pks: List[int]):
        if not finished:
            redis_instance.hdel(f"album_{album_pk}", "number_of_processed_photos",
                                "number_of_verified_patterns", "people_amount")
            redis_instance.delete(f"album_{album_pk}_finished")
        else:
            redis_instance.delete(f"album_{album_pk}")
        redis_instance.delete(f"album_{album_pk}_photos")
        redis_instance.delete(*[f"photo_{pk}" for pk in photo_pks])

        str_patterns = (f"album_{album_pk}_pattern_", f"album_{album_pk}_person_")
        for str_pattern in str_patterns:
            i = 1
            while redis_instance.exists(str_pattern + str(i)):
                redis_instance.delete(str_pattern + str(i))
                i += 1

    @staticmethod
    def encrease_patterns_search_amount(person_pk):
        redis_instance.incrby(f"person_{person_pk}_processed_patterns_amount")
        redis_instance.expire(f"person_{person_pk}_processed_patterns_amount", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def set_founded_similar_people(person_pk, pks):
        redis_instance.rpush(f"nearest_people_to_{person_pk}", *pks)
        redis_instance.delete(f"person_{person_pk}_processed_patterns_amount")
        redis_instance.expire(f"nearest_people_to_{person_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_founded_similar_people(person_pk):
        return list(map(int, redis_instance.lrange(f"nearest_people_to_{person_pk}", 0, -1)))

    @staticmethod
    def get_searched_patterns_amount(person_pk):
        return int(redis_instance.get(f"person_{person_pk}_processed_patterns_amount"))

    @staticmethod
    def prepare_to_search(person_pk):
        redis_instance.delete(f"nearest_people_to_{person_pk}")
        redis_instance.set(f"person_{person_pk}_processed_patterns_amount", 0)
        redis_instance.expire(f"person_{person_pk}_processed_patterns_amount", REDIS_DATA_EXPIRATION_SECONDS)


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
