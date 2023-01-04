import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'photoalbums.settings')

app = Celery('photoalbums')
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()
