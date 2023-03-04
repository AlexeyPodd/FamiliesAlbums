from django.contrib import admin

from .admin_models import AlbumsAdmin, PhotosAdmin
from .models import *

admin.site.register(Albums, AlbumsAdmin)
admin.site.register(Photos, PhotosAdmin)

admin.site.site_title = "Family Albums - Administration"
admin.site.site_header = "Family Albums site administration"
