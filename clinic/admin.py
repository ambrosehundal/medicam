from django.contrib import admin
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from django.utils.translation import gettext as _

from clinic.models import *

class SiteAdmin(admin.ModelAdmin):
	def get_queryset(self, request):
		qs = super(SiteAdmin, self).get_queryset(request)
		if not request.user.is_superuser:
			qs = qs.filter(site=get_current_site(request))
		return qs

class DoctorAdmin(SiteAdmin):
	list_display=('name', 'provider_type', 'verified', 'get_languages', 'push_token', 'in_session', 'last_seen')
	readonly_fields=('access_url', 'credentials', 'utc_offset', 'last_seen', 'last_notified', 'self_certification_questions', 'remarks', 'in_session', 'ip_address', 'user_agent')

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
		list_filter = ('verified', 'languages', 'provider_type')
		if request.user.is_superuser:
			list_filter += ('site',)
		return list_filter

	def get_exclude(self, request, obj=None):
		if not request.user.is_superuser:
			return ('site', 'email', 'fcm_token')
		else:
			return ()

class DisclaimerAdmin(SiteAdmin):
	pass

class PatientAdmin(SiteAdmin):
	list_display=('id', 'language', 'doctor', 'session_started', 'wait_duration', 'online')
	readonly_fields=('site', 'language', 'doctor', 'online', 'last_seen', 'session_started', 'session_ended', 'wait_duration', 'enable_video', 'text_only', 'feedback_response', 'feedback_text', 'ip_address')

	def get_list_filter(self, request):
		list_filter=('language', 'feedback_response')
		if request.user.is_superuser:
			list_filter += ('site',)
		return list_filter

	def has_add_permission(self, request, obj=None):
		return False

admin.site.register(Disclaimer, DisclaimerAdmin)
admin.site.register(Doctor, DoctorAdmin)
admin.site.register(Language)
admin.site.register(Patient, PatientAdmin)
admin.site.register(Report)
admin.site.register(SelfCertificationQuestion)
