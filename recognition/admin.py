from django.contrib import admin

from recognition.admin_models import PatternsAdmin, FacesAdmin, PeopleAdmin, ClustersAdmin
from recognition.models import Faces, Patterns, People, Clusters

admin.site.register(Faces, FacesAdmin)
admin.site.register(Patterns, PatternsAdmin)
admin.site.register(People, PeopleAdmin)
admin.site.register(Clusters, ClustersAdmin)
