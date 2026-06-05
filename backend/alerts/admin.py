from django.contrib import admin

from .models import Alert, AlertEntity

admin.site.register(Alert)
admin.site.register(AlertEntity)
