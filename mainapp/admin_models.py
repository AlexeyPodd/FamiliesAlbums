from django.contrib import admin
from django.utils.safestring import mark_safe


class AlbumsAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'owner_id', 'is_private', 'miniature', 'time_create')
    list_display_links = ('id', 'title')
    search_fields = ('title', 'owner_id')
    list_filter = ('time_create', 'time_update', 'is_private')
    prepopulated_fields = {'slug': ('title',)}
    fields = ('owner_id', 'title', 'slug', 'date_start', 'date_end', 'location', 'description',
              'is_private', 'miniature', 'time_create', 'time_update')
    readonly_fields = ('owner_id', 'is_private', 'time_create', 'time_update')
    save_on_top = True

    def get_html_miniature(self, object):
        if object.photo is not None:
            return mark_safe(f"<img src='{object.miniature.url}' width=50>")

    get_html_miniature.short_description = "Miniature"
