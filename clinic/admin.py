from django.contrib import admin

from clinic.models import Doctor, Language, Report, SelfCertificationQuestion

class DoctorAdmin(admin.ModelAdmin):
	list_display=('name', 'verified', 'get_languages', 'push_token', 'in_session')
	list_filter=('verified', 'languages')
	readonly_fields=('credentials', 'languages', 'utc_offset', 'last_online', 'last_notified', 'self_certification_questions', 'remarks', 'in_session', 'ip_address', 'user_agent', 'fcm_token')

	def get_languages(self, obj):
		return ", ".join([l.name for l in obj.languages.all()])
	get_languages.short_description = "Languages"

	def push_token(self, obj):
		return bool(obj.fcm_token)

admin.site.register(Doctor, DoctorAdmin)
admin.site.register(Language)
admin.site.register(Report)
admin.site.register(SelfCertificationQuestion)
