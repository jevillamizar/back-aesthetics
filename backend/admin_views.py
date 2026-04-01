import json
from datetime import date, datetime

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from appointments.models import Appointment
from landing.models import ClinicLanding
from patients.models import Patient
from treatments.models import Treatment
from .auth_views import get_auth_user


def _require_admin(request):
    """Return (user, error_response). If error_response is not None, return it."""
    user = get_auth_user(request)
    if user is None:
        return None, JsonResponse({'detail': 'Not authenticated'}, status=401)
    if user.role not in ('ADMIN',):
        return None, JsonResponse({'detail': 'Forbidden'}, status=403)
    return user, None


# ─── Landing ────────────────────────────────────────────────────────

LANDING_TEXT_FIELDS = [
    'headline', 'description',
    'primary_color', 'secondary_color', 'accent_color', 'background_color', 'text_color',
    'font_heading', 'font_body', 'font_accent',
    'about_title', 'about_subtitle', 'about_description',
    'about_badge_title', 'about_badge_text',
    'phone', 'email', 'whatsapp_phone', 'booking_url',
    'instagram_url', 'facebook_url', 'address',
]

LANDING_JSON_FIELDS = [
    'trust_indicators', 'testimonials', 'about_bullets',
]

LANDING_BOOL_FIELDS = ['is_published']

LANDING_IMAGE_FIELDS = ['logo', 'hero_image', 'about_image']


def _landing_to_dict(landing, request):
    data = {}
    for f in LANDING_TEXT_FIELDS:
        data[f] = getattr(landing, f, '') or ''
    for f in LANDING_JSON_FIELDS:
        data[f] = getattr(landing, f, []) or []
    for f in LANDING_BOOL_FIELDS:
        data[f] = getattr(landing, f, False)
    for f in LANDING_IMAGE_FIELDS:
        field = getattr(landing, f, None)
        if field:
            try:
                data[f'{f}_url'] = request.build_absolute_uri(field.url)
            except Exception:
                data[f'{f}_url'] = ''
        else:
            data[f'{f}_url'] = ''
    data['id'] = landing.id
    return data


@csrf_exempt
def admin_landing(request):
    user, err = _require_admin(request)
    if err:
        return err

    landing, _ = ClinicLanding.objects.get_or_create(defaults={})

    if request.method == 'GET':
        return JsonResponse({'landing': _landing_to_dict(landing, request)})

    if request.method == 'PUT':
        content_type = (request.content_type or '').lower()

        if 'multipart' in content_type:
            payload = request.POST.dict()
            files = request.FILES
        else:
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                return JsonResponse({'detail': 'Invalid JSON'}, status=400)
            files = {}

        for f in LANDING_TEXT_FIELDS:
            if f in payload:
                setattr(landing, f, payload[f])

        for f in LANDING_JSON_FIELDS:
            if f in payload:
                val = payload[f]
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except json.JSONDecodeError:
                        return JsonResponse({'detail': f'Invalid JSON for {f}'}, status=400)
                setattr(landing, f, val)

        for f in LANDING_BOOL_FIELDS:
            if f in payload:
                val = payload[f]
                if isinstance(val, str):
                    val = val.lower() in ('true', '1', 'yes')
                setattr(landing, f, bool(val))

        for f in LANDING_IMAGE_FIELDS:
            if f in files:
                setattr(landing, f, files[f])

        landing.save()
        return JsonResponse({'landing': _landing_to_dict(landing, request)})

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Treatments ─────────────────────────────────────────────────────

def _treatment_to_dict(t):
    return {
        'id': t.id,
        'name': t.name,
        'slug': t.slug,
        'category': t.category,
        'description': t.description,
        'duration_minutes': t.duration_minutes,
        'price': str(t.price) if t.price is not None else None,
        'is_active': t.is_active,
    }


@csrf_exempt
def admin_treatments(request):
    user, err = _require_admin(request)
    if err:
        return err

    if request.method == 'GET':
        qs = Treatment.objects.order_by('category', 'name')
        return JsonResponse({'treatments': [_treatment_to_dict(t) for t in qs]})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        name = (payload.get('name') or '').strip()
        if not name:
            return JsonResponse({'detail': 'name is required'}, status=400)

        t = Treatment.objects.create(
            name=name,
            slug=payload.get('slug', '').strip() or None,
            category=payload.get('category', '').strip(),
            description=payload.get('description', '').strip(),
            duration_minutes=payload.get('duration_minutes') or 30,
            price=payload.get('price'),
            is_active=payload.get('is_active', True),
        )
        return JsonResponse({'treatment': _treatment_to_dict(t)}, status=201)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_treatment_detail(request, treatment_id):
    user, err = _require_admin(request)
    if err:
        return err

    try:
        t = Treatment.objects.get(id=treatment_id)
    except Treatment.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'treatment': _treatment_to_dict(t)})

    if request.method == 'PUT':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        for field in ('name', 'slug', 'category', 'description'):
            if field in payload:
                setattr(t, field, (payload[field] or '').strip())
        if 'duration_minutes' in payload:
            t.duration_minutes = payload['duration_minutes'] or 30
        if 'price' in payload:
            t.price = payload['price']
        if 'is_active' in payload:
            t.is_active = bool(payload['is_active'])
        t.save()
        return JsonResponse({'treatment': _treatment_to_dict(t)})

    if request.method == 'DELETE':
        t.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Dashboard ───────────────────────────────────────────────────────

@csrf_exempt
def admin_dashboard(request):
    user, err = _require_admin(request)
    if err:
        return err

    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    appointments_today = Appointment.objects.filter(
        starts_at__gte=today_start,
        starts_at__lte=today_end,
    ).exclude(status=Appointment.Status.CANCELED).count()

    appointments_month = Appointment.objects.filter(
        starts_at__gte=month_start,
    ).exclude(status=Appointment.Status.CANCELED).count()

    patients_total = Patient.objects.count()
    treatments_active = Treatment.objects.filter(is_active=True).count()

    from datetime import timedelta
    five_days_later = now + timedelta(days=5)

    upcoming = (
        Appointment.objects
        .select_related('patient', 'treatment', 'doctor')
        .filter(starts_at__gte=now, starts_at__lte=five_days_later)
        .exclude(status=Appointment.Status.CANCELED)
        .order_by('starts_at')[:8]
    )

    upcoming_list = []
    for a in upcoming:
        upcoming_list.append({
            'id': a.id,
            'starts_at': a.starts_at.isoformat(),
            'ends_at': a.ends_at.isoformat(),
            'status': a.status,
            'patient_name': f"{a.patient.first_name} {a.patient.last_name}".strip() if a.patient else '—',
            'patient_email': a.patient.email if a.patient else '',
            'treatment_name': a.treatment.name if a.treatment else '—',
            'doctor_email': a.doctor.email if a.doctor else None,
            'notes': a.notes or '',
        })

    return JsonResponse({
        'stats': {
            'appointments_today': appointments_today,
            'appointments_month': appointments_month,
            'patients_total': patients_total,
            'treatments_active': treatments_active,
        },
        'upcoming_appointments': upcoming_list,
    })


# ─── Appointments ────────────────────────────────────────────────────

def _appointment_to_dict(a):
    return {
        'id': a.id,
        'starts_at': a.starts_at.isoformat(),
        'ends_at': a.ends_at.isoformat(),
        'status': a.status,
        'notes': a.notes or '',
        'patient_id': a.patient_id,
        'patient_name': f"{a.patient.first_name} {a.patient.last_name}".strip() if a.patient else '—',
        'patient_email': a.patient.email if a.patient else '',
        'patient_phone': a.patient.phone if a.patient else '',
        'treatment_id': a.treatment_id,
        'treatment_name': a.treatment.name if a.treatment else None,
        'doctor_id': a.doctor_id,
        'doctor_email': a.doctor.email if a.doctor else None,
    }


@csrf_exempt
def admin_appointments(request):
    user, err = _require_admin(request)
    if err:
        return err

    if request.method == 'GET':
        qs = (
            Appointment.objects
            .select_related('patient', 'treatment', 'doctor')
            .order_by('starts_at')
        )
        status_filter = request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        date_filter = request.GET.get('date')
        if date_filter:
            from django.utils.dateparse import parse_date as _pd
            d = _pd(date_filter)
            if d:
                qs = qs.filter(starts_at__date=d)
        patient_filter = request.GET.get('patient_id')
        if patient_filter:
            qs = qs.filter(patient_id=patient_filter)
        return JsonResponse({'appointments': [_appointment_to_dict(a) for a in qs]})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        from django.utils.dateparse import parse_datetime as _pdt
        from django.utils.timezone import is_naive, make_aware

        starts_at = _pdt(payload.get('starts_at') or '')
        ends_at = _pdt(payload.get('ends_at') or '')
        if not starts_at or not ends_at:
            return JsonResponse({'detail': 'starts_at and ends_at required (ISO-8601)'}, status=400)
        if is_naive(starts_at):
            starts_at = make_aware(starts_at)
        if is_naive(ends_at):
            ends_at = make_aware(ends_at)

        patient_id = payload.get('patient_id')
        if not patient_id:
            return JsonResponse({'detail': 'patient_id required'}, status=400)
        try:
            patient = Patient.objects.get(id=patient_id)
        except Patient.DoesNotExist:
            return JsonResponse({'detail': 'patient not found'}, status=400)

        treatment = None
        if payload.get('treatment_id'):
            try:
                treatment = Treatment.objects.get(id=payload['treatment_id'])
            except Treatment.DoesNotExist:
                return JsonResponse({'detail': 'treatment not found'}, status=400)

        from users.models import User
        doctor = None
        if payload.get('doctor_id'):
            try:
                doctor = User.objects.get(id=payload['doctor_id'])
            except User.DoesNotExist:
                pass

        a = Appointment.objects.create(
            patient=patient,
            treatment=treatment,
            doctor=doctor,
            starts_at=starts_at,
            ends_at=ends_at,
            status=payload.get('status') or Appointment.Status.SCHEDULED,
            notes=(payload.get('notes') or '').strip(),
        )
        a.refresh_from_db()
        a.patient = patient
        a.treatment = treatment
        a.doctor = doctor
        return JsonResponse({'appointment': _appointment_to_dict(a)}, status=201)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_appointment_detail(request, appointment_id):
    user, err = _require_admin(request)
    if err:
        return err

    try:
        a = Appointment.objects.select_related('patient', 'treatment', 'doctor').get(id=appointment_id)
    except Appointment.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'appointment': _appointment_to_dict(a)})

    if request.method == 'PUT':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        if a.status == Appointment.Status.CONFIRMED and set(payload.keys()) - {'status'}:
            return JsonResponse(
                {'detail': 'No se puede editar una cita confirmada.'},
                status=400,
            )

        from django.utils.dateparse import parse_datetime as _pdt
        from django.utils.timezone import is_naive, make_aware

        if 'starts_at' in payload:
            dt = _pdt(payload['starts_at'] or '')
            if dt:
                a.starts_at = make_aware(dt) if is_naive(dt) else dt
        if 'ends_at' in payload:
            dt = _pdt(payload['ends_at'] or '')
            if dt:
                a.ends_at = make_aware(dt) if is_naive(dt) else dt
        if 'status' in payload:
            a.status = payload['status']
        if 'notes' in payload:
            a.notes = (payload['notes'] or '').strip()
        if 'treatment_id' in payload:
            try:
                a.treatment = Treatment.objects.get(id=payload['treatment_id']) if payload['treatment_id'] else None
            except Treatment.DoesNotExist:
                return JsonResponse({'detail': 'treatment not found'}, status=400)
        if 'patient_id' in payload:
            try:
                a.patient = Patient.objects.get(id=payload['patient_id'])
            except Patient.DoesNotExist:
                return JsonResponse({'detail': 'patient not found'}, status=400)
        a.save()
        a.refresh_from_db()
        a = Appointment.objects.select_related('patient', 'treatment', 'doctor').get(id=appointment_id)
        return JsonResponse({'appointment': _appointment_to_dict(a)})

    if request.method == 'DELETE':
        a.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Patients (for dropdowns) ────────────────────────────────────────

@csrf_exempt
def admin_patients(request):
    user, err = _require_admin(request)
    if err:
        return err

    if request.method == 'GET':
        qs = Patient.objects.order_by('last_name', 'first_name').values(
            'id', 'first_name', 'last_name', 'email', 'phone', 'date_of_birth', 'notes'
        )
        return JsonResponse({'patients': list(qs)})

    return JsonResponse({'detail': 'Method not allowed'}, status=405)
