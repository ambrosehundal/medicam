from django.conf import settings
from django.contrib.sites.models import Site
from django.db import models
from django.db.models import ExpressionWrapper, F, IntegerField, Q, TimeField
from django.db.models.functions import Cast, Extract
from django.utils.translation import gettext as _

import os, uuid
from datetime import datetime, timedelta

class Participant(models.Model):
	uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
	created = models.DateTimeField(auto_now_add=True)
	last_updated = models.DateTimeField(auto_now=True)
	last_seen = models.DateTimeField(blank=True, null=True)
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

VERIFICATION_PROBLEM_CHOICES=(
	(0, "N/A"),
	#(1, "Submitted a resume or CV"),
	(2, "Submitted an unacceptable credential"),
	(3, "Fake or malicious submission"),
	(4, "Other"),
)

PROVIDER_TYPE_CHOICES = (
	(0, "Unknown"),
	(1, "Other"),
	(2, "Doctor"),
	(3, "Nurse"),
	(4, "Student")
)

class Doctor(Participant):
	name = models.CharField(max_length=70, verbose_name=_("full name"))
	email = models.EmailField(blank=True, null=True)
	credentials = models.FileField(upload_to=upload_filename, blank=True, null=True)
	verified = models.BooleanField(default=False, verbose_name=_("approved"), help_text=_("Allows the provider to receive calls."))
	verification_problem = models.PositiveIntegerField(default=0, choices=VERIFICATION_PROBLEM_CHOICES, verbose_name=_("reason for non-approval"), help_text=_("Set this if the provider cannot be approved."))
	languages = models.ManyToManyField(Language)
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
	provider_type = models.IntegerField(default=0, choices=PROVIDER_TYPE_CHOICES, verbose_name=_("Provider type"), help_text=_("Doctor, nurse or student"))

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

	@classmethod
	def notify_filter(self, qs):
		# start with those who want notifications and have a push token
		qs = qs.filter(verified=True, notify=True, fcm_token__isnull=False, last_seen__isnull=False)
		qs = qs.exclude(fcm_token='')

		# exclude those last notified within their notify_interval
		due_for_notification = Q(last_notified__isnull=True) | Q(notify_interval__lt=datetime.now()-F('last_notified'))

		# annotate with quiet time in UTC
		local_to_utc = lambda field: Extract(field, 'epoch') + (F('utc_offset') * 60)
		qs = qs.annotate(utc_quiet_time_start=local_to_utc('quiet_time_start'), utc_quiet_time_end=local_to_utc('quiet_time_end'))

		# filter out those currently in quiet time
		null_qt = Q(quiet_time_start__isnull=True) | Q(quiet_time_end__isnull=True)
		current_time = datetime.utcnow().time()
		current_time_epoch = (current_time.hour * 60 * 60) + (current_time.minute * 60) + current_time.second
		not_quiet_time = null_qt | Q(utc_quiet_time_start__gt=current_time_epoch, utc_quiet_time_end__lt=current_time_epoch)

		return qs.filter(due_for_notification & not_quiet_time).order_by('-last_seen')

	@classmethod
	def notify_object(self, queryset, frequency):
		if queryset.filter(last_notified__gt=datetime.now()-frequency).count() == 0:
			return self.notify_filter(queryset).order_by('last_notified').first()
		else:
			return False

FEEDBACK_CHOICES=(
	(0, "Yes"),
	(1, "No, there was a technical problem"),
	(2, "No, there was a problem with the volunteer")
)

PATIENT_OFFLINE_AFTER=timedelta(minutes=1)

class Patient(Participant):
	language = models.ForeignKey(Language, models.PROTECT)
	doctor = models.ForeignKey(Doctor, models.PROTECT, blank=True, null=True)
	session_started = models.DateTimeField(blank=True, null=True)
	session_ended = models.DateTimeField(blank=True, null=True)
	notes = models.TextField(blank=True, editable=False)
	enable_video = models.BooleanField()
	text_only = models.BooleanField(default=False)
	feedback_response = models.IntegerField(default=0, verbose_name=_("did everything go well?"), choices=FEEDBACK_CHOICES)
	feedback_text = models.TextField(blank=True, verbose_name=_("any feedback for us?"))

	def __str__(self):
		return str(self.id)

	@property
	def in_session(self):
		return hasattr(self, 'doctor') and self.session_started and not self.session_ended

	@property
	def online(self):
		return bool(self.last_seen) and self.last_seen + PATIENT_OFFLINE_AFTER > datetime.now()

	@property
	def wait_duration(self):
		if not self.last_seen:
			d = timedelta()
		elif not self.session_started and not self.online:
			d = self.last_seen - self.created
		elif self.session_started:
			d = self.session_started - self.created
		else:
			d = datetime.now() - self.created
		return d - timedelta(microseconds=d.microseconds)

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


class VolunteerUpdate(models.Model):
	"Updates to be shown on the Volunteer Homepage if they are active."
	active = models.BooleanField(default=False)
	message = models.TextField()
	timestamp = models.DateTimeField(auto_now_add=True)
