from datetime import datetime, timedelta
import json

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from clinic.forms import DoctorForm, FeedbackForm
from clinic.models import ChatMessage, Doctor, Language, Patient, SelfCertificationQuestion

from ipware import get_client_ip
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VideoGrant

SIX_MONTHS = 15552000
ONE_MONTH = 2629800

def index(request):
	doctor_id = request.COOKIES.get('doctor_id')
	if doctor_id:
		return redirect('consultation')
	else:
		return render(request, 'clinic/index.html')

def volunteer(request):
	if request.method == 'POST':
		form = DoctorForm(request.POST, request.FILES)
		if form.is_valid():
			doctor = form.save(commit=False)
			doctor.ip_address = get_client_ip(request)[0]
			doctor.user_agent = request.META.get('HTTP_USER_AGENT')
			doctor.save()
			form.save_m2m()
			response = redirect('consultation')
			response.set_cookie('doctor_id', doctor.uuid, max_age=SIX_MONTHS)
			return response
	else:
		form = DoctorForm()
		form.fields['self_certification_questions'].queryset = SelfCertificationQuestion.objects.filter(language=request.LANGUAGE_CODE)

	return render(request, 'clinic/volunteer.html', {'form': form})

def disclaimer(request):
	patient_id = request.COOKIES.get('patient_id')
	if patient_id:
		return redirect('consultation')

	if request.method == 'POST':
		lang = Language.objects.get(ietf_tag=request.LANGUAGE_CODE)
		video = request.POST.get('video') == '1'
		patient = Patient(ip_address=get_client_ip(request)[0], language=lang, enable_video=video)
		patient.save()
		response = redirect('consultation')
		response.set_cookie('patient_id', patient.uuid, max_age=ONE_MONTH)
		return response
	else:
		return render(request, 'clinic/disclaimer.html')

def consultation(request):
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
	if not doctor.verified:
		return render(request, 'clinic/unverified.html')

	doctor.last_online = datetime.now()
	doctor.save()

	if not doctor.patient:
		patient = Patient.objects.order_by('id').filter(language__in=doctor.languages.all(), session_started__isnull=True).first()
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

	return render(request, 'clinic/session_doctor.html', context={
		'video_data': {
			'token': doctor.twilio_jwt,
			'room': str(doctor.patient.uuid),
			'enable_local_video': True,
		},
	})

def consultation_patient(request, patient):
	if not patient.in_session:
		return render(request, 'clinic/waiting_patient.html')
	else:
		return render(request, 'clinic/session_patient.html', context={
			'doctor': patient.doctor,
			'video_data': {
				'token': patient.twilio_jwt,
				'room': str(patient.uuid),
				'enable_local_video': patient.enable_video,
			},
		})

@transaction.atomic
def finish(request):
	doctor_id = request.COOKIES.get('doctor_id')
	patient_id = request.COOKIES.get('patient_id')

	response = redirect('index')

	if patient_id:
		if request.method != 'POST':
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

	if doctor_id:
		try:
			doctor = Doctor.objects.get(uuid=doctor_id)
			patient = doctor.patient
			if patient:
				patient.session_ended = datetime.now()
				patient.save()
		except Doctor.DoesNotExist:	
			pass

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
			return HttpResponseBadRequest("no active session")
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
