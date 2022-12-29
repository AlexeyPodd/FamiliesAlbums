from django.contrib import admin

from .admin_models import AlbumsAdmin
from .models import *

admin.site.register(Albums, AlbumsAdmin)
