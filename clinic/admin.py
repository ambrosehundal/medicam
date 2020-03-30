import logging
from smtplib import SMTPException

from django.contrib import admin, messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from django.utils.translation import gettext as _

from clinic.models import *

logger = logging.getLogger(__name__)

class SiteAdmin(admin.ModelAdmin):
	def get_queryset(self, request):
		qs = super().get_queryset(request)
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

	def save_model(self, request, obj, form, change):
		if not request.user.is_superuser and not hasattr(obj, 'site'):
			obj.site = get_current_site(request)

		if 'verified' in form.changed_data and obj.verified is True:
			if obj.email:
				try:
					context = {
						'provider_name': obj.name,
						'provider_access_url': f'https://{request.get_host()}{self.access_url(obj)}'
					}
					msg_plain = render_to_string('clinic/provider_approval_email.txt', context)
					msg_html = render_to_string('clinic/provider_approval_email.html', context)
					send_mail(
						'Welcome to doc19.org!',
						msg_plain,
						'doc19.org team <contact@doc19.org>',
						[obj.email],
						html_message=msg_html
					)
					messages.success(request, f"An approval email has been sent to {obj.email}")
				except SMTPException as err:
					logger.info(err)
					messages.error(request, f"Error. Could not send an approval email to {obj.email} - {str(err)}")
			else:
				messages.warning(request, 'Could not send an approval email. No email address provided.')

		return super().save_model(request, obj, form, change)

class DisclaimerAdmin(SiteAdmin):
	def get_exclude(self, request, obj=None):
		if not request.user.is_superuser:
			return ('site',)
		else:
			return ()

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
admin.site.register(VolunteerUpdate)
