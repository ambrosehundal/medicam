from django.contrib import admin
from clinic.models import Doctor, Language, SelfCertificationQuestion

class DoctorAdmin(admin.ModelAdmin):
	list_display=('name', 'verified', 'get_languages', 'in_session')
	list_filter=('verified', 'languages')
	readonly_fields=('credentials', 'languages', 'last_online', 'last_notified', 'self_certification_questions', 'in_session', 'ip_address', 'user_agent', 'fcm_token')

	def get_languages(self, obj):
		return ", ".join([l.name for l in obj.languages.all()])
	get_languages.short_description = "Languages"

admin.site.register(Doctor, DoctorAdmin)
admin.site.register(Language)
admin.site.register(SelfCertificationQuestion)
