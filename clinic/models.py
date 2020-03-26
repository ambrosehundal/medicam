from django.contrib.sites.models import Site
from django.db import models
from django.utils.translation import gettext as _

import os, uuid
from datetime import timedelta

class Participant(models.Model):
	uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
	created = models.DateTimeField(auto_now_add=True)
	last_updated = models.DateTimeField(auto_now=True)
	ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name=_("IP address"))
	twilio_jwt = models.TextField(blank=True, null=True, editable=False)
	site = models.ForeignKey(Site, on_delete=models.CASCADE)

	class Meta:
 		abstract = True

class Language(models.Model):
	ietf_tag = models.CharField(max_length=5, unique=True)
	name = models.CharField(max_length=30)

	class Meta:
		ordering = ['name']

	def __str__(self):
		return self.name

class SelfCertificationQuestion(models.Model):
	sort_order = models.PositiveIntegerField(default=0)
	text = models.TextField()
	language = models.ForeignKey(Language, models.PROTECT, to_field='ietf_tag', default='en')

	class Meta:
		ordering = ('sort_order',)

	def __str__(self):
		return self.text

def upload_filename(instance, filename):
	ext = os.path.splitext(filename)[-1].lower()
	return 'credentials/{}{}'.format(instance.uuid, ext)

class Doctor(Participant):
	name = models.CharField(max_length=70, verbose_name=_("full name"))
	email = models.EmailField(blank=True, null=True)
	credentials = models.FileField(upload_to=upload_filename, blank=True, null=True)
	verified = models.BooleanField(default=False, verbose_name=_("active"), help_text=_("Allows the provider to receive calls."))
	languages = models.ManyToManyField(Language)
	last_online = models.DateTimeField(blank=True, null=True)
	last_notified = models.DateTimeField(blank=True, null=True)
	notify = models.BooleanField(default=True, verbose_name=_("send notifications"), help_text=_("Not yet implemented"))
	notify_interval = models.DurationField(blank=True, null=True, verbose_name=_("notify me no more than once every"), default=timedelta(hours=6))
	quiet_time_start = models.TimeField(blank=True, null=True, verbose_name=_("start of quiet hours"))
	quiet_time_end = models.TimeField(blank=True, null=True, verbose_name=_("end of quiet hours"))
	fcm_token = models.TextField(blank=True, null=True, verbose_name=_("FCM push token"))
	self_certification_questions = models.ManyToManyField(SelfCertificationQuestion, blank=True)
	user_agent = models.TextField(blank=True, null=True)
	remarks = models.TextField(blank=True, verbose_name=_("anything to add?"))
	utc_offset = models.IntegerField(default=0, verbose_name=_("UTC offset"))

	class Meta:
		verbose_name = "provider"

	def __str__(self):
		return self.name

	@property
	def patient(self):
		try:
			return self.patient_set.get(session_started__isnull=False, session_ended__isnull=True)
		except Patient.DoesNotExist:
			return None

	@property
	def in_session(self):
		return self.patient_set.filter(session_started__isnull=False, session_ended__isnull=True).count() > 0

FEEDBACK_CHOICES=(
	(0, 'Yes'),
	(1, 'No, there was a technical problem'),
	(2, 'No, there was a problem with the volunteer')
)

class Patient(Participant):
	language = models.ForeignKey(Language, models.PROTECT)
	doctor = models.ForeignKey(Doctor, models.PROTECT, blank=True, null=True)
	session_started = models.DateTimeField(blank=True, null=True)
	session_ended = models.DateTimeField(blank=True, null=True)
	notes = models.TextField(blank=True)
	enable_video = models.BooleanField()
	text_only = models.BooleanField(default=False)
	feedback_response = models.IntegerField(default=0, verbose_name=_("did everything go well?"), choices=FEEDBACK_CHOICES)
	feedback_text = models.TextField(blank=True, verbose_name=_("any feedback for us?"))

	@property
	def in_session(self):
		return hasattr(self, 'doctor') and self.session_started and not self.session_ended

class Report(models.Model):
	by_doctor = models.ForeignKey(Doctor, models.PROTECT, blank=True, null=True)
	by_patient = models.ForeignKey(Patient, models.PROTECT, blank=True, null=True)
	against_patient = models.ForeignKey(Patient, models.PROTECT, blank=True, null=True, related_name='reported_by')
	reason = models.TextField(blank=True)
	timestamp = models.DateTimeField(auto_now_add=True)

class ChatMessage(models.Model):
	uuid = models.UUIDField(unique=True, editable=False)
	doctor = models.ForeignKey(Doctor, models.CASCADE, blank=True, null=True, to_field='uuid')
	patient = models.ForeignKey(Patient, models.CASCADE, blank=True, null=True, to_field='uuid')
	text = models.TextField()
	sent = models.DateTimeField(auto_now_add=True)
	read = models.DateTimeField(blank=True, null=True)

class Disclaimer(models.Model):
	site = models.ForeignKey(Site, on_delete=models.CASCADE)
	html = models.TextField(verbose_name=_("HTML"))

	def __str__(self):
		return str(self.site)
