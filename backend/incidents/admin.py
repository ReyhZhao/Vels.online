from django.contrib import admin

from .models import Incident, IncidentEvent

admin.site.register(Incident)
admin.site.register(IncidentEvent)
