from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe

from photoalbums.settings import CLUSTER_LIMIT
from recognition.models import Faces


class PeopleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'get_albums_amount', 'owner', 'get_patterns_amount', 'get_photos_amount')
    list_display_links = ('id', 'name')
    search_fields = ('name', 'owner')
    fields = ('name', 'slug', 'get_albums_amount', 'owner', 'get_patterns_amount', 'get_photos_amount')
    readonly_fields = ('slug', 'get_albums_amount', 'owner', 'get_patterns_amount', 'get_photos_amount')

    def get_albums_amount(self, obj):
        faces = Faces.objects.filter(pattern__person__pk=obj.pk)
        return len(set((face.photo.album.pk for face in faces)))

    def get_patterns_amount(self, obj):
        return obj.patterns_set.count()

    def get_photos_amount(self, obj):
        return Faces.objects.filter(pattern__person__pk=obj.pk).count()

    get_albums_amount.short_description = "Albums amount"
    get_patterns_amount.short_description = "Patterns contained amount"
    get_photos_amount.short_description = "Photos amount"


class PatternsAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_central_face_image', 'get_cluster_level', 'person', 'get_owner', 'get_faces_amount',
                    'get_albums_amount')
    search_fields = ('get_owner',)
    list_filter = ('person',)
    fields = ('get_central_face_image', 'get_cluster_level', 'person', 'get_owner', 'get_faces_amount',
              'get_albums_amount')
    readonly_fields = ('get_central_face_image', 'get_cluster_level', 'person', 'get_owner', 'get_faces_amount',
                       'get_albums_amount')

    def get_central_face_image(self, obj):
        face_url = reverse('get_face_img') + f'?face={obj.central_face.slug}'
        return mark_safe(f"<img src='{face_url}' width=50>")

    def get_cluster_level(self, obj):
        cluster = obj.cluster
        count = 0
        while cluster.parent:
            cluster = cluster.parent
            count += 1
        return count

    def get_owner(self, obj):
        return obj.person.owner

    def get_faces_amount(self, obj):
        return obj.faces_set.count()

    def get_albums_amount(self, obj):
        faces = obj.faces_set.all()
        return len(set((face.photo.album.pk for face in faces)))

    get_central_face_image.short_description = "Central face image"
    get_cluster_level.short_description = "Cluster level"
    get_owner.short_description = "Owner"
    get_faces_amount.short_description = "Faces amount"
    get_albums_amount.short_description = "Albums amount"


class FacesAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_image', 'photo', 'get_album', 'get_owner', 'pattern', 'get_person')
    search_fields = ('photo', 'get_album', 'get_owner', 'get_person')
    list_filter = ('pattern', 'photo')
    fields = ('get_image', 'photo', 'get_album', 'get_owner', 'pattern', 'get_person')
    readonly_fields = ('get_image', 'photo', 'get_album', 'get_owner', 'pattern', 'get_person')

    def get_image(self, obj):
        face_url = reverse('get_face_img') + f'?face={obj.slug}'
        return mark_safe(f"<img src='{face_url}' width=50>")

    def get_album(self, obj):
        return obj.photo.album

    def get_owner(self, obj):
        return obj.photo.album.owner

    def get_person(self, obj):
        return obj.pattern.person

    get_image.short_description = "Image"
    get_album.short_description = "Album"
    get_owner.short_description = "Owner"
    get_person.short_description = "Person"


class ClustersAdmin(admin.ModelAdmin):
    list_display = ('id', 'parent_id', 'get_occupancy_degree', 'get_child_cluster_amount', 'get_level')
    search_fields = ('id',)
    list_filter = ('parent_id',)
    fields = ('parent_id', 'get_occupancy_degree', 'get_child_cluster_amount', 'get_level')
    readonly_fields = ('parent_id', 'get_occupancy_degree', 'get_child_cluster_amount', 'get_level')

    def get_occupancy_degree(self, obj):
        return round((obj.clusters_set.count() + obj.patterns_set.count()) / CLUSTER_LIMIT * 100, 2)

    def get_child_cluster_amount(self, obj):
        return obj.clusters_set.count()

    def get_level(self, obj):
        cluster = obj
        count = 0
        while cluster.parent:
            cluster = cluster.parent
            count += 1
        return count

    get_occupancy_degree.short_description = "Occupancy"
    get_child_cluster_amount.short_description = "Child clusters amount"
    get_level.short_description = "Level in tree"
