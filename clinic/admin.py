from django.contrib import admin
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse

from clinic.models import Disclaimer, Doctor, Language, Report, SelfCertificationQuestion

class DoctorAdmin(admin.ModelAdmin):
	list_display=('name', 'verified', 'get_languages', 'push_token', 'in_session')
	list_filter=('verified', 'languages', 'site')
	readonly_fields=('access_url', 'credentials', 'utc_offset', 'last_online', 'last_notified', 'self_certification_questions', 'remarks', 'in_session', 'ip_address', 'user_agent', 'fcm_token')

	def get_languages(self, obj):
		return ", ".join([l.name for l in obj.languages.all()])
	get_languages.short_description = "Languages"

	def push_token(self, obj):
		return bool(obj.fcm_token)

	def access_url(self, obj):
		return reverse('consultation') + '?provider_id=' + str(obj.uuid)
	access_url.short_description = "Access URL"

	def get_list_filter(self, request):
		list_filter = ('verified', 'languages')
		if request.user.is_superuser:
			list_filter += ('site',)
		return list_filter

	def get_queryset(self, request):
		qs = super(DoctorAdmin, self).get_queryset(request)
		if not request.user.is_superuser:
			qs = qs.filter(site=get_current_site(request))
		return qs

admin.site.register(Disclaimer)
admin.site.register(Doctor, DoctorAdmin)
admin.site.register(Language)
admin.site.register(Report)
admin.site.register(SelfCertificationQuestion)
