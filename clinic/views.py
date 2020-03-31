from datetime import datetime, timedelta
import json, logging

from django.conf import settings
from django.core.mail import mail_admins
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from clinic.forms import FeedbackForm, OrgRequestForm, VolunteerForm
from clinic.models import PATIENT_OFFLINE_AFTER
from clinic.models import (
	ChatMessage,
	Disclaimer,
	Doctor,
	Language,
	Patient,
	SelfCertificationQuestion,
	VolunteerUpdate,
)

from firebase_admin import messaging
from ipware import get_client_ip
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VideoGrant

SIX_MONTHS = 15552000
ONE_MONTH = 2629800

logger = logging.getLogger(__name__)

def primary_site_only(func):
	def wrapper(request):
		site = get_current_site(request)
		if site.id == 1:
			return func(request)
		else:
			return redirect('consultation')
	return wrapper

@primary_site_only
def index(request):
	doctor_id = request.COOKIES.get('doctor_id')
	if doctor_id:
		return volunteer_homepage(request)
	else:
		return render(request, 'clinic/index.html')

@primary_site_only
def volunteer_homepage(request):
	return render(request, 'clinic/volunteer_homepage.html', {
		'updates': VolunteerUpdate.objects.filter(active=True).order_by('-timestamp'),
	})

@primary_site_only
def volunteer(request):
	if request.method == 'POST':
		form = VolunteerForm(request.POST, request.FILES)
		if form.is_valid():
			doctor = form.save(commit=False)
			doctor.ip_address = get_client_ip(request)[0]
			doctor.user_agent = request.META.get('HTTP_USER_AGENT')
			doctor.site = get_current_site(request)
			doctor.save()
			form.save_m2m()
			response = redirect('consultation')
			response.set_cookie('doctor_id', doctor.uuid, max_age=SIX_MONTHS)
			return response
	else:
		form = VolunteerForm()
		form.fields['self_certification_questions'].queryset = SelfCertificationQuestion.objects.filter(language=request.LANGUAGE_CODE)

	return render(request, 'clinic/volunteer_form.html', {'form': form})

def disclaimer(request):
	patient_id = request.COOKIES.get('patient_id')
	if patient_id:
		return redirect('consultation')

	site = get_current_site(request)

	if request.method == 'POST':
		lang = Language.objects.get(ietf_tag=request.LANGUAGE_CODE)
		video = request.POST.get('video') == '1'
		patient = Patient(ip_address=get_client_ip(request)[0], language=lang, enable_video=video)
		patient.site = site
		patient.save()
		response = redirect('consultation')
		response.set_cookie('patient_id', patient.uuid, max_age=ONE_MONTH)
		return response
	else:
		obj = Disclaimer.objects.filter(site=site).first()
		return render(request, 'clinic/disclaimer.html', {'disclaimer': obj})

def consultation(request):
	provider_id = request.GET.get('provider_id')
	if provider_id:
		response = redirect('consultation')
		response.set_cookie('doctor_id', provider_id, max_age=SIX_MONTHS)
		return response

	doctor_id = request.COOKIES.get('doctor_id')
	if doctor_id:
		try:
			doctor = Doctor.objects.get(uuid=doctor_id)
		except Doctor.DoesNotExist:
			response = redirect('consultation')
			response.delete_cookie('doctor_id')
			return response
		return consultation_doctor(request, doctor)

	patient_id = request.COOKIES.get('patient_id')
	if patient_id:
		try:
			patient = Patient.objects.get(uuid=patient_id, session_ended__isnull=True)
		except Patient.DoesNotExist:
			response = redirect('consultation')
			response.delete_cookie('patient_id')
			return response
		return consultation_patient(request, patient)

	return redirect('disclaimer')

def get_twilio_jwt(identity, room):
	token = AccessToken(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_API_KEY, settings.TWILIO_API_SECRET, identity=identity)
	token.add_grant(VideoGrant(room=room))
	return token.to_jwt().decode('utf-8')

@transaction.atomic
def consultation_doctor(request, doctor):
	doctor.last_seen = datetime.now()
	doctor.save()

	if not doctor.verified:
		return render(request, 'clinic/unverified.html')

	if not doctor.patient:
		patient = Patient.objects.order_by('id').filter(site=doctor.site, language__in=doctor.languages.all(), session_started__isnull=True, last_seen__gt=datetime.now()-PATIENT_OFFLINE_AFTER).first()
		if patient:
			patient.doctor = doctor
			patient.session_started = datetime.now()
			patient.twilio_jwt = get_twilio_jwt(identity=str(patient.uuid), room=str(patient.uuid))
			patient.save()
			doctor.twilio_jwt = get_twilio_jwt(identity=str(doctor.id), room=str(patient.uuid))
			doctor.save()
			return redirect('consultation')
		else:
			return render(request, 'clinic/waiting_doctor.html')

	return render(request, 'clinic/session.html', context={
		'user_type': 'doctor',
		'video_data': {
			'token': doctor.twilio_jwt,
			'room': str(doctor.patient.uuid),
			'enable_local_video': True,
			'user_type': 'doctor',
		},
	})

def send_notification(doctor, patient):
	doctor.last_notified = datetime.now()
	doctor.save()

	logger.info("Patient is waiting, sending notification to {} (waiting for {})".format(doctor, patient.wait_duration))

	wait_minutes = int(patient.wait_duration.total_seconds() / 60)
	if wait_minutes <= 1:
		wait_minutes_str = "1 minute"
	else:
		wait_minutes_str = "{} minutes".format(wait_minutes)

	message = messaging.Message(
		notification=messaging.Notification(
			title="Incoming call on doc19.org",
			body="Someone has been waiting for {}".format(wait_minutes_str),
		),
		token=settings.TEST_FCM_TOKEN or doctor.fcm_token,
	)

	response = messaging.send(message)
	logger.info("Sent notification to {}: {}".format(doctor, response))

SEND_FIRST_NOTIFICATION_AFTER=timedelta(seconds=30)
NOTIFICATION_FREQUENCY=timedelta(minutes=3)

def maybe_send_notification(request, patient):
	# don't start sending notifications until the patient has been waiting for a minimum amount of time
	if patient.wait_duration < SEND_FIRST_NOTIFICATION_AFTER:
		return

	doctors = Doctor.objects.filter(site=get_current_site(request), languages=patient.language)
	doctor = Doctor.notify_object(doctors, NOTIFICATION_FREQUENCY)
	if doctor:
		send_notification(doctor, patient)
	elif doctor is None:
		# notify_object returns False if a doctor was last notified within the frequency,
		# or None if a notification should be sent but no doctor is eligible for notifications
		logger.warning("Patient is waiting, but there's no {}-speaking doctor to notify".format(patient.language))

@transaction.atomic
def consultation_patient(request, patient):
	patient.last_seen = datetime.now()
	patient.save()

	if not patient.in_session:
		maybe_send_notification(request, patient)
		return render(request, 'clinic/waiting_patient.html')
	else:
		return render(request, 'clinic/session.html', context={
			'user_type': 'patient',
			'doctor': patient.doctor,
			'video_data': {
				'token': patient.twilio_jwt,
				'room': str(patient.uuid),
				'enable_local_video': patient.enable_video,
				'user_type': 'patient',
			},
		})

@transaction.atomic
def finish(request):
	response = redirect('index')
	if request.method != 'POST':
		return response

	doctor_id = request.COOKIES.get('doctor_id')
	patient_id = request.COOKIES.get('patient_id')

	if doctor_id:
		try:
			doctor = Doctor.objects.get(uuid=doctor_id)
			patient = doctor.patient
			if patient:
				patient.session_ended = datetime.now()
				patient.save()
		except Doctor.DoesNotExist:
			pass

		if 'stop_consulting' in request.POST:
			return response
		else:
			return redirect(consultation)

	elif patient_id:
		if 'end_session' in request.POST:
			return render(request, 'clinic/finish.html', {'form': FeedbackForm()})
		response.delete_cookie('patient_id')
		try:
			patient = Patient.objects.get(uuid=patient_id)
		except Patient.DoesNotExist:
			return response
		form = FeedbackForm(request.POST, instance=patient)
		if form.is_valid():
			patient = form.save(commit=False)
			patient.session_ended = datetime.now()
			patient.save()
			form.save_m2m()
		else:
			return render(request, 'clinic/finish.html', {'form': form})


	return response

@require_http_methods(['GET', 'POST'])
def chat(request):
	patient_id = request.COOKIES.get('patient_id')
	doctor_id = request.COOKIES.get('doctor_id')

	if patient_id:
		patient = Patient(uuid=patient_id)
	elif doctor_id:
		try:
			patient = Patient.objects.only('uuid').get(doctor__uuid=doctor_id, session_started__isnull=False, session_ended__isnull=True)
		except Patient.DoesNotExist:
			return HttpResponseNotFound("no active session")
	else:
		return HttpResponseBadRequest("patient_id or doctor_id required")

	if request.method == 'POST':
		return chat_post(request, patient.uuid, doctor_id)

	messages = []
	for msg in ChatMessage.objects.order_by('sent').filter(patient__uuid=patient.uuid):
		if (msg.doctor and doctor_id) or (not msg.doctor and patient_id):
			name = _("You")
		elif msg.doctor:
			name = msg.doctor.name
		else:
			name = _("Visitor")

		messages.append({
			'uuid': msg.uuid,
			'name': name,
			'time': msg.sent.timestamp() * 1000, # JS uses milliseconds
			'text': msg.text,
		})

	return JsonResponse({'messages': messages})

def chat_post(request, patient_id, doctor_id):
	json_data = json.loads(request.body.decode('utf-8'))
	msg = ChatMessage(patient_id=patient_id, uuid=json_data.get('uuid'), text=json_data.get('text'))
	if doctor_id:
		msg.doctor_id = doctor_id
	msg.save()
	return HttpResponse(status=200)

@login_required
def submit_org(request):
	if request.method == 'POST':
		form = OrgRequestForm(request.POST)
		if form.is_valid():
			form.cleaned_data['username'] = request.user.get_username()
			mail_admins("Organization request", str(form.cleaned_data))
	else:
		form = OrgRequestForm()
	return render(request, 'clinic/submit_org.html', {'form': form})
