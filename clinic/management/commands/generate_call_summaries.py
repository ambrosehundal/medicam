from clinic.models import *
from django.core.management.base import BaseCommand, CommandError

def strip_microseconds(d):
	return d - timedelta(microseconds=d.microseconds)

class Command(BaseCommand):
	def handle(self, *args, **kwargs):
		for patient in Patient.objects.filter(callsummary__duration__isnull=True):
			self.update_summary(patient)

	def update_summary(self, patient):
		try:
			summary = patient.callsummary
		except CallSummary.DoesNotExist:
			summary = CallSummary(site=patient.site, patient=patient)

		first_event = None

		for e in patient.call_events.order_by('timestamp'):
			if not first_event:
				first_event = e.timestamp

			if e.participant_id == str(patient.uuid):
				if not summary.patient_connected and e.event == EVENT_PARTICIPANT_CONNECTED:
					summary.patient_connected = strip_microseconds(e.timestamp - first_event)
				elif not summary.patient_audio_start and e.event == EVENT_TRACK_ADDED and e.track_kind == TRACK_AUDIO:
					summary.patient_audio_start = strip_microseconds(e.timestamp - first_event)
				elif not summary.patient_video_start and e.event == EVENT_TRACK_ADDED and e.track_kind == TRACK_VIDEO:
					summary.patient_video_start = strip_microseconds(e.timestamp - first_event)

			elif e.participant_id == str(patient.doctor.id):
				if not summary.doctor_connected and e.event == EVENT_PARTICIPANT_CONNECTED:
					summary.doctor_connected = strip_microseconds(e.timestamp - first_event)
				elif not summary.doctor_audio_start and e.event == EVENT_TRACK_ADDED and e.track_kind == TRACK_AUDIO:
					summary.doctor_audio_start = strip_microseconds(e.timestamp - first_event)
				elif not summary.doctor_video_start and e.event == EVENT_TRACK_ADDED and e.track_kind == TRACK_VIDEO:
					summary.doctor_video_start = strip_microseconds(e.timestamp - first_event)

			elif e.event == EVENT_PARTICIPANT_DISCONNECTED or (not summary.duration and e.event == EVENT_ROOM_ENDED):
				summary.duration = strip_microseconds(e.timestamp - first_event)

		if first_event:
			summary.save()
			self.stdout.write(self.style.SUCCESS(f"Updated call summary for patient {patient.id}."))
		else:
			self.stdout.write(self.style.WARNING(f"No events for patient {patient.id}."))
