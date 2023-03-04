from django.contrib import admin
from django.utils.safestring import mark_safe

from recognition.models import Faces


class AlbumsAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'owner', 'is_private', 'get_html_miniature_cover', 'get_photos_amount',
                    'time_create')
    list_display_links = ('id', 'title')
    search_fields = ('title', 'owner')
    list_filter = ('time_create', 'time_update', 'is_private')
    fields = ('owner', 'title', 'slug', 'date_start', 'date_end', 'location', 'description', 'is_private',
              'get_html_miniature_cover', 'get_photos_amount', 'time_create', 'time_update', 'are_all_photos_processed',
              'get_people_amount')
    readonly_fields = ('owner', 'is_private', 'time_create', 'time_update', 'slug', 'get_html_miniature_cover',
                       'get_photos_amount', 'are_all_photos_processed', 'get_people_amount')
    save_on_top = True

    def get_html_miniature_cover(self, obj):
        if obj.miniature:
            return mark_safe(f"<img src='{obj.miniature.original.url}' width=50>")
            
    def get_photos_amount(self, obj):
        return obj.photos_set.count()

    def are_all_photos_processed(self, obj):
        return obj.photos_set.count() == obj.photos_set.filter(faces_extracted=True).count()

    def get_people_amount(self, obj):
        if obj.photos_set.filter(faces_extracted=True).exists():
            return len(set((face.pattern.person.pk for face in Faces.objects.filter(photo__album__pk=obj.pk))))

    are_all_photos_processed.short_description = "Fully processed"
    get_html_miniature_cover.short_description = "Cover"
    get_photos_amount.short_description = "Photos amount"
    get_people_amount.short_description = "People founded"


class PhotosAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'album', 'get_owner', 'is_private', 'get_html_miniature', 'time_create')
    list_display_links = ('id', 'title')
    search_fields = ('title', 'get_owner', 'album')
    list_filter = ('time_create', 'time_update', 'is_private')
    fields = ('title', 'slug', 'get_owner', 'album', 'date_start', 'date_end', 'location', 'description',
              'is_private', 'faces_extracted', 'get_people_amount', 'time_create', 'time_update')
    readonly_fields = ('slug', 'get_owner', 'album', 'is_private', 'faces_extracted', 'get_people_amount',
                       'time_create', 'time_update')
    save_on_top = True

    def get_owner(self, obj):
        return obj.album.owner

    def get_html_miniature(self, obj):
        return mark_safe(f"<img src='{obj.original.url}' width=50>")

    def get_people_amount(self, obj):
        if obj.faces_extracted:
            return obj.faces_set.count()

    get_owner.short_description = "Owner"
    get_html_miniature.short_description = "Miniature"
    get_people_amount.short_description = "Founded people amount"
