import json

from django.http import JsonResponse
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import is_naive, make_aware
from django.views.decorators.csrf import csrf_exempt

from appointments.models import Appointment
from landing.models import ClinicLanding
from patients.models import Patient
from treatments.models import Treatment


def tenant_debug(request):
    clinic = getattr(request, 'clinic', None)
    return JsonResponse(
        {
            'host': request.get_host(),
            'subdomain': getattr(request, 'subdomain', None),
            'clinic': (
                None
                if clinic is None
                else {
                    'id': clinic.id,
                    'name': clinic.name,
                    'slug': clinic.slug,
                }
            ),
        }
    )


@csrf_exempt
def public_create_appointment(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    clinic = getattr(request, 'clinic', None)
    if clinic is None:
        return JsonResponse({'detail': 'Clinic not resolved from host'}, status=400)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    patient_payload = payload.get('patient') or {}
    first_name = (patient_payload.get('first_name') or '').strip()
    last_name = (patient_payload.get('last_name') or '').strip()
    phone = (patient_payload.get('phone') or '').strip()
    email = (patient_payload.get('email') or '').strip()
    date_of_birth_raw = (patient_payload.get('date_of_birth') or '').strip()

    if not first_name or not last_name:
        return JsonResponse({'detail': 'patient.first_name and patient.last_name are required'}, status=400)

    date_of_birth = parse_date(date_of_birth_raw) if date_of_birth_raw else None
    if date_of_birth_raw and date_of_birth is None:
        return JsonResponse({'detail': 'patient.date_of_birth must be YYYY-MM-DD'}, status=400)

    starts_at_raw = (payload.get('starts_at') or '').strip()
    ends_at_raw = (payload.get('ends_at') or '').strip()

    starts_at = parse_datetime(starts_at_raw) if starts_at_raw else None
    ends_at = parse_datetime(ends_at_raw) if ends_at_raw else None

    if starts_at is None or ends_at is None:
        return JsonResponse({'detail': 'starts_at and ends_at are required (ISO-8601)'}, status=400)

    if is_naive(starts_at):
        starts_at = make_aware(starts_at)
    if is_naive(ends_at):
        ends_at = make_aware(ends_at)

    if ends_at <= starts_at:
        return JsonResponse({'detail': 'ends_at must be after starts_at'}, status=400)

    patient = None
    if email:
        patient, _ = Patient.objects.get_or_create(
            clinic=clinic,
            email=email,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'phone': phone,
                'date_of_birth': date_of_birth,
            },
        )
    elif phone:
        patient = (
            Patient.objects.filter(
                clinic=clinic,
                phone=phone,
                first_name=first_name,
                last_name=last_name,
            )
            .order_by('-id')
            .first()
        )

    if patient is None:
        patient = Patient.objects.create(
            clinic=clinic,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            date_of_birth=date_of_birth,
        )

    treatment_id = payload.get('treatment_id')
    treatment_slug = (payload.get('treatment_slug') or '').strip()
    treatment = None
    if treatment_id is not None:
        try:
            treatment = Treatment.objects.get(id=treatment_id, clinic=clinic)
        except Treatment.DoesNotExist:
            return JsonResponse({'detail': 'treatment_id not found for this clinic'}, status=400)
    elif treatment_slug:
        try:
            treatment = Treatment.objects.get(clinic=clinic, slug=treatment_slug)
        except Treatment.DoesNotExist:
            return JsonResponse({'detail': 'treatment_slug not found for this clinic'}, status=400)

    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        doctor=None,
        treatment=treatment,
        starts_at=starts_at,
        ends_at=ends_at,
        status=Appointment.Status.SCHEDULED,
        notes=(payload.get('notes') or '').strip(),
    )

    return JsonResponse(
        {
            'id': appointment.id,
            'clinic_id': clinic.id,
            'patient_id': patient.id,
            'doctor_id': appointment.doctor_id,
            'treatment_id': appointment.treatment_id,
            'starts_at': appointment.starts_at.isoformat(),
            'ends_at': appointment.ends_at.isoformat(),
            'status': appointment.status,
        },
        status=201,
    )


def public_treatments(request):
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    clinic = getattr(request, 'clinic', None)
    if clinic is None:
        return JsonResponse({'detail': 'Clinic not resolved from host'}, status=400)

    treatments = (
        Treatment.objects.filter(clinic=clinic, is_active=True)
        .order_by('category', 'name')
        .values('id', 'name', 'slug', 'category', 'description', 'duration_minutes', 'price')
    )

    return JsonResponse({'results': list(treatments)})


def public_landing(request):
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    clinic = getattr(request, 'clinic', None)
    if clinic is None:
        return JsonResponse({'detail': 'Clinic not resolved from host'}, status=400)

    landing = (
        ClinicLanding.objects.filter(clinic=clinic)
        .order_by('-updated_at')
        .first()
    )

    if landing is not None and not landing.is_published:
        return JsonResponse({'detail': 'Landing not published'}, status=404)

    logo_url = ''
    hero_image_url = ''
    if landing is not None and getattr(landing, 'logo', None):
        try:
            logo_url = request.build_absolute_uri(landing.logo.url)
        except Exception:
            logo_url = ''
    if landing is not None and getattr(landing, 'hero_image', None):
        try:
            hero_image_url = request.build_absolute_uri(landing.hero_image.url)
        except Exception:
            hero_image_url = ''

    return JsonResponse(
        {
            'clinic': {
                'id': clinic.id,
                'name': clinic.name,
                'slug': clinic.slug,
            },
            'landing': (
                None
                if landing is None
                else {
                    'headline': landing.headline,
                    'description': landing.description,
                    'primary_color': landing.primary_color,
                    'secondary_color': landing.secondary_color,
                    'accent_color': landing.accent_color,
                    'background_color': landing.background_color,
                    'text_color': landing.text_color,
                    'font_heading': landing.font_heading,
                    'font_body': landing.font_body,
                    'font_accent': landing.font_accent,
                    'logo_url': logo_url,
                    'hero_image_url': hero_image_url,
                    'trust_indicators': landing.trust_indicators or [],
                    'testimonials': landing.testimonials or [],
                    'phone': landing.phone,
                    'email': landing.email,
                    'whatsapp_phone': landing.whatsapp_phone,
                    'booking_url': landing.booking_url,
                    'instagram_url': landing.instagram_url,
                    'facebook_url': landing.facebook_url,
                    'address': landing.address,
                }
            ),
        }
    )
