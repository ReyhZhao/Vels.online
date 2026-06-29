from django.contrib import admin

from .models import Incident, IncidentEvent, Subject, TaskTemplate, TaskTemplateItem, Task, Comment

admin.site.register(Incident)
admin.site.register(IncidentEvent)
admin.site.register(Subject)
admin.site.register(TaskTemplate)
admin.site.register(TaskTemplateItem)
admin.site.register(Task)
admin.site.register(Comment)

