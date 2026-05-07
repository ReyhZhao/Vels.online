from django.contrib import admin

from .models import Incident, IncidentEvent, Subject, TaskTemplate, TaskTemplateItem

admin.site.register(Incident)
admin.site.register(IncidentEvent)
admin.site.register(Subject)
admin.site.register(TaskTemplate)
admin.site.register(TaskTemplateItem)
