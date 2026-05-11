import json
from datetime import timedelta

from django.http import JsonResponse
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import is_naive, make_aware
from django.views.decorators.csrf import csrf_exempt

from appointments.models import Appointment
from landing.models import ClinicLanding
from leads.models import Lead
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
                phone=phone,
                first_name=first_name,
                last_name=last_name,
            )
            .order_by('-id')
            .first()
        )

    if patient is None:
        patient = Patient.objects.create(
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
            treatment = Treatment.objects.get(id=treatment_id)
        except Treatment.DoesNotExist:
            return JsonResponse({'detail': 'treatment_id not found'}, status=400)
    elif treatment_slug:
        try:
            treatment = Treatment.objects.get(slug=treatment_slug)
        except Treatment.DoesNotExist:
            return JsonResponse({'detail': 'treatment_slug not found'}, status=400)

    appointment = Appointment.objects.create(
        patient=patient,
        doctor=None,
        treatment=treatment,
        starts_at=starts_at,
        ends_at=ends_at,
        status=Appointment.Status.PENDING,
        notes=(payload.get('notes') or '').strip(),
    )

    return JsonResponse(
        {
            'id': appointment.id,
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

    treatments = (
        Treatment.objects.filter(is_active=True)
        .order_by('category', 'name')
        .values('id', 'name', 'slug', 'category', 'description', 'long_description', 'duration_minutes', 'price', 'image_url')
    )

    return JsonResponse({'results': list(treatments)})


def public_availability(request):
    """
    GET /public/availability/?date=YYYY-MM-DD[&duration=60]
    Returns free slots for the given date using Google Calendar freebusy.
    Falls back to an empty list if GCal is not connected.
    """
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    date_raw = (request.GET.get('date') or '').strip()
    if not date_raw:
        return JsonResponse({'detail': 'date query param required (YYYY-MM-DD)'}, status=400)

    target_date = parse_date(date_raw)
    if target_date is None:
        return JsonResponse({'detail': 'date must be YYYY-MM-DD'}, status=400)

    try:
        duration_minutes = max(15, int(request.GET.get('duration') or 0))
    except (ValueError, TypeError):
        duration_minutes = 0  # fallback to service default

    try:
        from gcal.service import get_free_slots
        slots = get_free_slots(target_date, duration_minutes=duration_minutes or None)
    except Exception:
        slots = []

    return JsonResponse({'date': date_raw, 'slots': slots})


@csrf_exempt
def public_create_lead(request):
    """
    POST /public/leads/
    Creates a Lead + Appointment (type=VALORACION) and books the slot in Google Calendar.

    Required body:
    {
      "first_name": "Ana",
      "last_name": "Gómez",
      "phone": "+57 300 000 0000",
      "email": "ana@example.com",       # optional but recommended
      "interest_notes": "Quiero info sobre botox",
      "starts_at": "2025-05-10T09:00:00Z",
      "ends_at":   "2025-05-10T10:00:00Z"
    }
    """
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    first_name     = (payload.get('first_name') or '').strip()
    last_name      = (payload.get('last_name') or '').strip()
    phone          = (payload.get('phone') or '').strip()
    email          = (payload.get('email') or '').strip()
    interest_notes = (payload.get('interest_notes') or '').strip()

    if not first_name or not last_name:
        return JsonResponse({'detail': 'first_name and last_name are required'}, status=400)
    if not phone and not email:
        return JsonResponse({'detail': 'phone or email is required'}, status=400)

    starts_at_raw = (payload.get('starts_at') or '').strip()
    ends_at_raw   = (payload.get('ends_at') or '').strip()

    starts_at = parse_datetime(starts_at_raw) if starts_at_raw else None
    ends_at   = parse_datetime(ends_at_raw)   if ends_at_raw   else None

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
            email=email,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'phone': phone,
            },
        )
    elif phone:
        patient = (
            Patient.objects.filter(phone=phone, first_name=first_name, last_name=last_name)
            .order_by('-id')
            .first()
        )

    if patient is None:
        patient = Patient.objects.create(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
        )

    appointment = Appointment.objects.create(
        patient=patient,
        doctor=None,
        treatment=None,
        appointment_type=Appointment.AppointmentType.VALORACION,
        starts_at=starts_at,
        ends_at=ends_at,
        status=Appointment.Status.PENDING,
        notes=interest_notes,
    )

    google_event_id = None
    try:
        from gcal.service import create_event
        summary     = f"Valoración — {first_name} {last_name}"
        description = interest_notes or f"Tel: {phone}"
        google_event_id = create_event(starts_at, ends_at, summary, description)
        if google_event_id:
            appointment.google_event_id = google_event_id
            appointment.save(update_fields=['google_event_id'])
    except Exception:
        pass

    lead = Lead.objects.create(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        interest_notes=interest_notes,
        source=Lead.Source.LANDING,
        status=Lead.Status.NEW,
        appointment=appointment,
        patient=patient,
    )

    return JsonResponse(
        {
            'lead_id': lead.id,
            'appointment_id': appointment.id,
            'patient_id': patient.id,
            'starts_at': appointment.starts_at.isoformat(),
            'ends_at': appointment.ends_at.isoformat(),
            'google_event_id': google_event_id,
        },
        status=201,
    )


def public_landing(request):
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    landing = (
        ClinicLanding.objects.order_by('-updated_at')
        .first()
    )

    if landing is not None and not landing.is_published:
        return JsonResponse({'detail': 'Landing not published'}, status=404)

    hero_image_url = ''
    if landing is not None and getattr(landing, 'hero_image', None):
        try:
            hero_image_url = request.build_absolute_uri(landing.hero_image.url)
        except Exception:
            hero_image_url = ''

    about_image_url = ''
    if landing is not None and getattr(landing, 'about_image', None):
        try:
            about_image_url = request.build_absolute_uri(landing.about_image.url)
        except Exception:
            about_image_url = ''

    # Get clinic info for top-bar branding
    clinic = getattr(request, 'clinic', None)

    # Build clinic logo URL from ImageField
    clinic_logo_url = ''
    if clinic and getattr(clinic, 'logo', None):
        try:
            clinic_logo_url = request.build_absolute_uri(clinic.logo.url)
        except Exception:
            clinic_logo_url = ''

    return JsonResponse(
        {
            'clinic': (
                None
                if clinic is None
                else {
                    'id': clinic.id,
                    'name': clinic.name,
                    'slug': clinic.slug,
                    'logo_url': clinic_logo_url,
                }
            ),
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
                    'show_name': landing.show_name,
                    'show_logo': landing.show_logo,
                    'hero_image_url': hero_image_url,
                    'hero_image_urls': landing.hero_image_urls or [],
                    'trust_indicators': landing.trust_indicators or [],
                    'testimonials': landing.testimonials or [],
                    'about_title': landing.about_title,
                    'about_subtitle': landing.about_subtitle,
                    'about_description': landing.about_description,
                    'about_bullets': landing.about_bullets or [],
                    'about_image_url': about_image_url,
                    'about_image_urls': landing.about_image_urls or [],
                    'about_badge_title': landing.about_badge_title,
                    'about_badge_text': landing.about_badge_text,
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


def public_team(request):
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    from users.models import User

    doctors = User.objects.filter(role=User.Role.DOCTOR, is_active=True).order_by('last_name', 'first_name')

    team = []
    for doc in doctors:
        photo_url = ''
        if getattr(doc, 'photo', None):
            try:
                photo_url = request.build_absolute_uri(doc.photo.url)
            except Exception:
                photo_url = ''
        team.append({
            'id': doc.id,
            'first_name': doc.first_name or '',
            'last_name': doc.last_name or '',
            'profession': doc.profession or '',
            'specialty': doc.specialty or '',
            'bio': doc.bio or '',
            'photo_url': photo_url,
        })

    return JsonResponse({'team': team})
