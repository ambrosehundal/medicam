from django.contrib import admin
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from django.utils.translation import gettext as _

from clinic.models import Disclaimer, Doctor, Language, Report, SelfCertificationQuestion

class SiteAdmin(admin.ModelAdmin):
	def get_queryset(self, request):
		qs = super(SiteAdmin, self).get_queryset(request)
		if not request.user.is_superuser:
			qs = qs.filter(site=get_current_site(request))
		return qs

class DoctorAdmin(SiteAdmin):
	list_display=('name', 'verified', 'get_languages', 'push_token', 'in_session')
	list_filter=('verified', 'languages', 'site')
	readonly_fields=('access_url', 'credentials', 'utc_offset', 'last_online', 'last_notified', 'self_certification_questions', 'remarks', 'in_session', 'ip_address', 'user_agent', 'fcm_token')

	def get_languages(self, obj):
		return ", ".join([l.name for l in obj.languages.all()])
	get_languages.short_description = "Languages"

	def push_token(self, obj):
		return bool(obj.fcm_token)

	def access_url(self, obj):
		if obj.pk:
			return reverse('consultation') + '?provider_id=' + str(obj.uuid)
		else:
			return _("(will be generated when provider is added)")
	access_url.short_description = "Access URL"

	def get_list_filter(self, request):
		list_filter = ('verified', 'languages')
		if request.user.is_superuser:
			list_filter += ('site',)
		return list_filter

class DisclaimerAdmin(SiteAdmin):
	pass

admin.site.register(Disclaimer, DisclaimerAdmin)
admin.site.register(Doctor, DoctorAdmin)
admin.site.register(Language)
admin.site.register(Report)
admin.site.register(SelfCertificationQuestion)
