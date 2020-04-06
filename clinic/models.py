from django.conf import settings
from django.contrib.sites.models import Site
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Extract
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
	language = models.ForeignKey(Language, on_delete=models.PROTECT, to_field='ietf_tag', default='en')

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
	verified = models.BooleanField(default=False, verbose_name=_("approved"), help_text=_("Allows the provider to receive calls. Approving a provider will trigger an email to be sent to them."))
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
	provider_type = models.IntegerField(default=0, choices=PROVIDER_TYPE_CHOICES, verbose_name=_("provider type"), help_text=_("Doctor, nurse or student"))

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
		return self.patient_set.filter(session_started__isnull=False, session_ended__isnull=True).exists()

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
		if not queryset.filter(last_notified__gt=datetime.now()-frequency).exists():
			return self.notify_filter(queryset).order_by('last_notified').first()
		else:
			return False

FEEDBACK_CHOICES=(
	(0, "Yes"),
	(1, "No, there was a technical problem"),
	(2, "No, there was a problem with the volunteer")
)

PATIENT_OFFLINE_AFTER=timedelta(seconds=25)

class Patient(Participant):
	language = models.ForeignKey(Language, on_delete=models.PROTECT)
	doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, blank=True, null=True)
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

	@property
	def call_events(self):
		return CallEvent.objects.filter(room_name=str(self.uuid))

	@property
	def track_added(self):
		return self.call_events.filter(event=EVENT_TRACK_ADDED).exists()

	@classmethod
	def get_queue(self, qs):
		# must be unmatched and currently online
		return qs.filter(session_started__isnull=True, last_seen__gt=datetime.now()-PATIENT_OFFLINE_AFTER).order_by('id')

class Report(models.Model):
	by_doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, blank=True, null=True)
	by_patient = models.ForeignKey(Patient, on_delete=models.PROTECT, blank=True, null=True)
	against_patient = models.ForeignKey(Patient, on_delete=models.PROTECT, blank=True, null=True, related_name='reported_by')
	reason = models.TextField(blank=True)
	timestamp = models.DateTimeField(auto_now_add=True)

class ChatMessage(models.Model):
	uuid = models.UUIDField(unique=True, editable=False)
	doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, blank=True, null=True, to_field='uuid')
	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, blank=True, null=True, to_field='uuid')
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

EVENT_ROOM_CREATED = "room-created"
EVENT_ROOM_ENDED = "room-ended"
EVENT_PARTICIPANT_CONNECTED = "participant-connected"
EVENT_PARTICIPANT_DISCONNECTED = "participant-disconnected"
EVENT_TRACK_ADDED = "track-added"
EVENT_TRACK_REMOVED = "track-removed"

EVENT_CHOICES=(
	(EVENT_ROOM_CREATED, "room created"),
	(EVENT_ROOM_ENDED, "room ended"),
	(EVENT_PARTICIPANT_CONNECTED, "participant connected"),
	(EVENT_PARTICIPANT_DISCONNECTED, "participant disconnected"),
	(EVENT_TRACK_ADDED, "track added"),
	(EVENT_TRACK_REMOVED, "track removed"),
)

ROOM_IN_PROGRESS = "in-progress"
ROOM_FAILED = "failed"
ROOM_COMPLETED = "completed"

ROOM_STATUS_CHOICES=(
	(ROOM_IN_PROGRESS, "in progress"),
	(ROOM_FAILED, "failed"),
	(ROOM_COMPLETED, "completed"),
)

PARTICIPANT_CONNECTED = "connected"
PARTICIPANT_DISCONNECTED = "disconnected"

PARTICIPANT_STATUS_CHOICES=(
	(PARTICIPANT_CONNECTED, "connected"),
	(PARTICIPANT_DISCONNECTED, "disconnected"),
)

TRACK_DATA = "data"
TRACK_AUDIO = "audio"
TRACK_VIDEO = "video"

TRACK_CHOICES=(
	(TRACK_DATA, "data"),
	(TRACK_AUDIO, "audio"),
	(TRACK_VIDEO, "video"),
)

class CallEvent(models.Model):
	received = models.DateTimeField(auto_now_add=True)
	event = models.CharField(max_length=50, choices=EVENT_CHOICES)
	room_name = models.CharField(max_length=254, db_index=True)
	room_status = models.CharField(max_length=20, choices=ROOM_STATUS_CHOICES)
	room_duration = models.DurationField(blank=True, null=True)
	timestamp = models.DateTimeField()
	participant_status = models.CharField(max_length=20, blank=True, null=True, choices=PARTICIPANT_STATUS_CHOICES)
	participant_id = models.CharField(max_length=254, blank=True, null=True)
	participant_duration = models.DurationField(blank=True, null=True)
	track_kind = models.CharField(max_length=20, blank=True, null=True, choices=TRACK_CHOICES)

	def __str__(self):
		return "{} {} @ {}".format(self.room_name, self.event, self.timestamp)

SUCCESSFUL_CALL_DURATION=timedelta(seconds=30)

class CallSummary(models.Model):
	site = models.ForeignKey(Site, on_delete=models.CASCADE)
	patient = models.OneToOneField(Patient, on_delete=models.PROTECT)
	created = models.DateTimeField(auto_now_add=True, verbose_name=_("summary created"))
	last_updated = models.DateTimeField(auto_now=True, verbose_name=_("summary last updated"))
	first_event = models.DateTimeField()
	doctor_connected = models.DurationField(blank=True, null=True, verbose_name=_("provider connected"))
	doctor_audio_start = models.DurationField(blank=True, null=True, verbose_name=_("provider video started"))
	doctor_video_start = models.DurationField(blank=True, null=True, verbose_name=_("provider audio started"))
	patient_connected = models.DurationField(blank=True, null=True, verbose_name=_("caller connected"))
	patient_audio_start = models.DurationField(blank=True, null=True, verbose_name=_("caller video started"))
	patient_video_start = models.DurationField(blank=True, null=True, verbose_name=_("caller audio started"))
	duration = models.DurationField(blank=True, null=True)

	class Meta:
		verbose_name_plural = _("call summaries")

	def __str__(self):
		return str(self.patient)

	@property
	def successful(self):
		return bool(
			self.patient_audio_start
			and (self.patient_video_start or not self.enable_video)
			and self.doctor_audio_start
			and self.doctor_video_start
			and self.duration
			and self.duration > SUCCESSFUL_CALL_DURATION
		)
