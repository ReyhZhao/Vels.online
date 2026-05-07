from django.contrib import admin

from .models import Incident, IncidentEvent, Subject

admin.site.register(Incident)
admin.site.register(IncidentEvent)
admin.site.register(Subject)
