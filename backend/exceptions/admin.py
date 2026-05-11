from django.contrib import admin

from .models import ExceptionRule, FreedRuleId, WazuhRuleIdPool

admin.site.register(ExceptionRule)
admin.site.register(WazuhRuleIdPool)
admin.site.register(FreedRuleId)
