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

    _auto_no_show()
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

    import calendar as _cal
    last_day = _cal.monthrange(now.year, now.month)[1]
    month_end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)

    upcoming = (
        Appointment.objects
        .select_related('patient', 'treatment', 'doctor')
        .filter(starts_at__gte=month_start, starts_at__lte=month_end)
        .exclude(status=Appointment.Status.CANCELED)
        .order_by('starts_at')
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

def _auto_no_show():
    from django.utils import timezone as _tz
    _now = _tz.now()
    Appointment.objects.filter(
        starts_at__lt=_now,
        status=Appointment.Status.SCHEDULED,
    ).update(status=Appointment.Status.NO_SHOW)


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
        _auto_no_show()
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
        doctor_filter = request.GET.get('doctor_id')
        if doctor_filter:
            qs = qs.filter(doctor_id=doctor_filter)
        from_date = request.GET.get('from')
        to_date = request.GET.get('to')
        if from_date:
            from django.utils.dateparse import parse_date as _pd2
            fd = _pd2(from_date)
            if fd:
                qs = qs.filter(starts_at__date__gte=fd)
        if to_date:
            from django.utils.dateparse import parse_date as _pd3
            td = _pd3(to_date)
            if td:
                qs = qs.filter(starts_at__date__lte=td)
        if request.GET.get('past') == '1':
            qs = (
                Appointment.objects
                .select_related('patient', 'treatment', 'doctor')
                .filter(status__in=['COMPLETED', 'CANCELED', 'NO_SHOW'])
                .order_by('-starts_at')
            )
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

        LOCKED_STATUSES = {Appointment.Status.CONFIRMED, Appointment.Status.COMPLETED}
        ALLOWED_ON_LOCKED = {'status', 'notes'}
        if a.status in LOCKED_STATUSES and set(payload.keys()) - ALLOWED_ON_LOCKED:
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


# ─── Patients ────────────────────────────────────────────────────────

def _patient_to_dict(p, request=None):
    if p.photo:
        try:
            photo_url = p.photo.url
            if request:
                photo_url = request.build_absolute_uri(photo_url)
        except Exception:
            photo_url = None
    else:
        photo_url = None
    return {
        'id': p.id,
        'document_type': p.document_type or '',
        'document_number': p.document_number or '',
        'first_name': p.first_name,
        'last_name': p.last_name,
        'date_of_birth': p.date_of_birth.isoformat() if p.date_of_birth else None,
        'sex': p.sex or '',
        'phone': p.phone or '',
        'email': p.email or '',
        'address': p.address or '',
        'photo': photo_url,
        'eps': p.eps or '',
        'legal_guardian': p.legal_guardian or '',
        'emergency_contact_name': p.emergency_contact_name or '',
        'emergency_contact_phone': p.emergency_contact_phone or '',
        'emergency_contact_relation': p.emergency_contact_relation or '',
        'notes': p.notes or '',
        'created_at': p.created_at.isoformat() if p.created_at else None,
    }


@csrf_exempt
def admin_patients(request):
    user, err = _require_admin(request)
    if err:
        return err

    if request.method == 'GET':
        search = request.GET.get('search', '').strip()
        qs = Patient.objects.order_by('last_name', 'first_name')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search) |
                Q(email__icontains=search) | Q(phone__icontains=search) |
                Q(document_number__icontains=search)
            )
        return JsonResponse({'patients': [_patient_to_dict(p, request) for p in qs]})

    if request.method == 'POST':
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
        first = (payload.get('first_name') or '').strip()
        last = (payload.get('last_name') or '').strip()
        if not first or not last:
            return JsonResponse({'detail': 'first_name and last_name required'}, status=400)
        from django.utils.dateparse import parse_date as _pd
        dob = _pd(payload.get('date_of_birth') or '') if payload.get('date_of_birth') else None
        p = Patient.objects.create(
            document_type=(payload.get('document_type') or '').strip(),
            document_number=(payload.get('document_number') or '').strip(),
            first_name=first,
            last_name=last,
            date_of_birth=dob,
            sex=(payload.get('sex') or '').strip(),
            phone=(payload.get('phone') or '').strip(),
            email=(payload.get('email') or '').strip(),
            address=(payload.get('address') or '').strip(),
            eps=(payload.get('eps') or '').strip(),
            legal_guardian=(payload.get('legal_guardian') or '').strip(),
            emergency_contact_name=(payload.get('emergency_contact_name') or '').strip(),
            emergency_contact_phone=(payload.get('emergency_contact_phone') or '').strip(),
            emergency_contact_relation=(payload.get('emergency_contact_relation') or '').strip(),
            notes=(payload.get('notes') or '').strip(),
        )
        if 'photo' in files:
            p.photo = files['photo']
            p.save()
        return JsonResponse({'patient': _patient_to_dict(p, request)}, status=201)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_patient_detail(request, patient_id):
    user, err = _require_admin(request)
    if err:
        return err
    try:
        p = Patient.objects.get(id=patient_id)
    except Patient.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'patient': _patient_to_dict(p, request)})

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
        if 'document_type' in payload:
            p.document_type = (payload['document_type'] or '').strip()
        if 'document_number' in payload:
            p.document_number = (payload['document_number'] or '').strip()
        if 'first_name' in payload:
            p.first_name = (payload['first_name'] or '').strip()
        if 'last_name' in payload:
            p.last_name = (payload['last_name'] or '').strip()
        if 'date_of_birth' in payload:
            from django.utils.dateparse import parse_date as _pd
            p.date_of_birth = _pd(payload['date_of_birth'] or '') if payload['date_of_birth'] else None
        if 'sex' in payload:
            p.sex = (payload['sex'] or '').strip()
        if 'phone' in payload:
            p.phone = (payload['phone'] or '').strip()
        if 'email' in payload:
            p.email = (payload['email'] or '').strip()
        if 'address' in payload:
            p.address = (payload['address'] or '').strip()
        if 'eps' in payload:
            p.eps = (payload['eps'] or '').strip()
        if 'legal_guardian' in payload:
            p.legal_guardian = (payload['legal_guardian'] or '').strip()
        if 'emergency_contact_name' in payload:
            p.emergency_contact_name = (payload['emergency_contact_name'] or '').strip()
        if 'emergency_contact_phone' in payload:
            p.emergency_contact_phone = (payload['emergency_contact_phone'] or '').strip()
        if 'emergency_contact_relation' in payload:
            p.emergency_contact_relation = (payload['emergency_contact_relation'] or '').strip()
        if 'notes' in payload:
            p.notes = (payload['notes'] or '').strip()
        if 'photo' in files:
            p.photo = files['photo']
        elif payload.get('photo') == '':
            p.photo = None
        p.save()
        return JsonResponse({'patient': _patient_to_dict(p, request)})

    if request.method == 'DELETE':
        p.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Doctors (Users with role=DOCTOR) ────────────────────────────────

def _doctor_to_dict(u):
    return {
        'id': u.id,
        'first_name': u.first_name or '',
        'last_name': u.last_name or '',
        'email': u.email,
        'is_active': u.is_active,
    }


@csrf_exempt
def admin_doctors(request):
    user, err = _require_admin(request)
    if err:
        return err

    from users.models import User as _User

    if request.method == 'GET':
        search = request.GET.get('search', '').strip()
        qs = _User.objects.filter(role=_User.Role.DOCTOR).order_by('last_name', 'first_name', 'email')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )
        return JsonResponse({'doctors': [_doctor_to_dict(u) for u in qs]})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)
        email = (payload.get('email') or '').strip()
        password = (payload.get('password') or '').strip()
        if not email or not password:
            return JsonResponse({'detail': 'email and password required'}, status=400)
        if _User.objects.filter(email=email).exists():
            return JsonResponse({'detail': 'Email already in use'}, status=400)
        doc = _User.objects.create_user(
            email=email,
            password=password,
            first_name=(payload.get('first_name') or '').strip(),
            last_name=(payload.get('last_name') or '').strip(),
            role=_User.Role.DOCTOR,
        )
        return JsonResponse({'doctor': _doctor_to_dict(doc)}, status=201)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_doctor_detail(request, doctor_id):
    user, err = _require_admin(request)
    if err:
        return err

    from users.models import User as _User
    try:
        doc = _User.objects.get(id=doctor_id, role=_User.Role.DOCTOR)
    except _User.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'doctor': _doctor_to_dict(doc)})

    if request.method == 'PUT':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)
        if 'first_name' in payload:
            doc.first_name = (payload['first_name'] or '').strip()
        if 'last_name' in payload:
            doc.last_name = (payload['last_name'] or '').strip()
        if 'email' in payload:
            new_email = (payload['email'] or '').strip()
            if new_email and new_email != doc.email:
                if _User.objects.filter(email=new_email).exists():
                    return JsonResponse({'detail': 'Email already in use'}, status=400)
                doc.email = new_email
        if 'is_active' in payload:
            doc.is_active = bool(payload['is_active'])
        if payload.get('password'):
            doc.set_password(payload['password'].strip())
        doc.save()
        return JsonResponse({'doctor': _doctor_to_dict(doc)})

    if request.method == 'DELETE':
        doc.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Revenue ──────────────────────────────────────────────────────────

@csrf_exempt
def admin_revenue(request):
    user, err = _require_admin(request)
    if err:
        return err
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    from medical_records.models import MedicalRecord, MedicalRecordTreatment
    from django.db.models import Sum, F, ExpressionWrapper, DecimalField as _Dec
    from django.db.models.functions import TruncMonth

    year = request.GET.get('year')
    try:
        year = int(year) if year else timezone.now().year
    except ValueError:
        year = timezone.now().year

    # Revenue from medical record treatment items
    items_qs = MedicalRecordTreatment.objects.filter(
        medical_record__appointment__starts_at__year=year,
        medical_record__appointment__status=Appointment.Status.COMPLETED,
    ).select_related('medical_record__appointment', 'treatment')

    revenue_expr = ExpressionWrapper(
        F('price') * F('quantity'), output_field=_Dec(max_digits=14, decimal_places=2)
    )

    # Monthly breakdown
    monthly_raw = (
        items_qs
        .annotate(month=TruncMonth('medical_record__appointment__starts_at'))
        .values('month')
        .annotate(total=Sum(revenue_expr))
        .order_by('month')
    )
    monthly = [
        {'month': row['month'].strftime('%Y-%m'), 'total': float(row['total'] or 0)}
        for row in monthly_raw
    ]

    # Fill missing months with 0
    monthly_map = {r['month']: r['total'] for r in monthly}
    monthly_full = []
    for m in range(1, 13):
        key = f'{year}-{m:02d}'
        monthly_full.append({'month': key, 'total': monthly_map.get(key, 0)})

    # Top treatments
    top_treatments = (
        items_qs
        .values(name=F('treatment__name'))
        .annotate(total=Sum(revenue_expr))
        .order_by('-total')[:8]
    )
    top_treatments_list = [{'name': r['name'], 'total': float(r['total'] or 0)} for r in top_treatments]

    # Top doctors
    top_doctors = (
        items_qs
        .values(email=F('medical_record__doctor__email'),
                first=F('medical_record__doctor__first_name'),
                last=F('medical_record__doctor__last_name'))
        .annotate(total=Sum(revenue_expr))
        .order_by('-total')[:6]
    )
    top_doctors_list = [
        {'name': f"{r['first']} {r['last']}".strip() or r['email'], 'total': float(r['total'] or 0)}
        for r in top_doctors
    ]

    total_year = sum(r['total'] for r in monthly_full)

    # Count of completed appointments for the year
    completed_count = Appointment.objects.filter(
        starts_at__year=year,
        status=Appointment.Status.COMPLETED,
    ).count()

    return JsonResponse({
        'year': year,
        'total': total_year,
        'completed_appointments': completed_count,
        'avg_per_appointment': round(total_year / completed_count, 2) if completed_count else 0,
        'monthly': monthly_full,
        'top_treatments': top_treatments_list,
        'top_doctors': top_doctors_list,
    })


# ─── Medical Records ──────────────────────────────────────────────────

def _medical_record_to_dict(rec):
    items = rec.treatment_items.select_related('treatment').all()
    return {
        'id': rec.id,
        'patient_id': rec.patient_id,
        'patient_name': f"{rec.patient.first_name} {rec.patient.last_name}".strip() if rec.patient else '—',
        'doctor_id': rec.doctor_id,
        'doctor_name': f"{rec.doctor.first_name} {rec.doctor.last_name}".strip() or rec.doctor.email if rec.doctor else '—',
        'appointment_id': rec.appointment_id,
        'chief_complaint': rec.chief_complaint or '',
        'current_illness': rec.current_illness or '',
        'personal_history': rec.personal_history or '',
        'surgical_history': rec.surgical_history or '',
        'allergic_history': rec.allergic_history or '',
        'pharmacological_history': rec.pharmacological_history or '',
        'family_history': rec.family_history or '',
        'physical_exam': rec.physical_exam or '',
        'diagnosis': rec.diagnosis or '',
        'treatment_plan': rec.treatment_plan or '',
        'evolution': rec.evolution or '',
        'informed_consent': rec.informed_consent or '',
        'consent_signed': rec.consent_signed,
        'notes': rec.notes or '',
        'created_at': rec.created_at.isoformat(),
        'treatment_items': [
            {
                'id': it.id,
                'treatment_id': it.treatment_id,
                'treatment_name': it.treatment.name if it.treatment else '—',
                'quantity': it.quantity,
                'price': float(it.price),
                'notes': it.notes or '',
            }
            for it in items
        ],
    }


@csrf_exempt
def admin_medical_records(request):
    user, err = _require_admin(request)
    if err:
        return err

    from medical_records.models import MedicalRecord, MedicalRecordTreatment

    if request.method == 'GET':
        patient_id = request.GET.get('patient_id')
        search = request.GET.get('search', '').strip()
        qs = (
            MedicalRecord.objects
            .select_related('patient', 'doctor', 'appointment')
            .prefetch_related('treatment_items__treatment')
            .order_by('-created_at')
        )
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(chief_complaint__icontains=search) |
                Q(diagnosis__icontains=search)
            )
        return JsonResponse({'records': [_medical_record_to_dict(r) for r in qs]})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        patient_id = payload.get('patient_id')
        doctor_id = payload.get('doctor_id')
        if not patient_id or not doctor_id:
            return JsonResponse({'detail': 'patient_id and doctor_id required'}, status=400)

        try:
            patient = Patient.objects.get(id=patient_id)
        except Patient.DoesNotExist:
            return JsonResponse({'detail': 'Patient not found'}, status=400)

        from users.models import User as _User
        try:
            doctor = _User.objects.get(id=doctor_id)
        except _User.DoesNotExist:
            return JsonResponse({'detail': 'Doctor not found'}, status=400)

        appointment = None
        if payload.get('appointment_id'):
            try:
                appointment = Appointment.objects.get(id=payload['appointment_id'])
            except Appointment.DoesNotExist:
                pass

        rec = MedicalRecord.objects.create(
            patient=patient,
            doctor=doctor,
            appointment=appointment,
            chief_complaint=(payload.get('chief_complaint') or '').strip(),
            current_illness=(payload.get('current_illness') or '').strip(),
            personal_history=(payload.get('personal_history') or '').strip(),
            surgical_history=(payload.get('surgical_history') or '').strip(),
            allergic_history=(payload.get('allergic_history') or '').strip(),
            pharmacological_history=(payload.get('pharmacological_history') or '').strip(),
            family_history=(payload.get('family_history') or '').strip(),
            physical_exam=(payload.get('physical_exam') or '').strip(),
            diagnosis=(payload.get('diagnosis') or '').strip(),
            treatment_plan=(payload.get('treatment_plan') or '').strip(),
            evolution=(payload.get('evolution') or '').strip(),
            informed_consent=(payload.get('informed_consent') or '').strip(),
            consent_signed=bool(payload.get('consent_signed', False)),
            notes=(payload.get('notes') or '').strip(),
        )

        for item in payload.get('treatment_items', []):
            tid = item.get('treatment_id')
            if not tid:
                continue
            try:
                t = Treatment.objects.get(id=tid)
            except Treatment.DoesNotExist:
                continue
            MedicalRecordTreatment.objects.create(
                medical_record=rec,
                treatment=t,
                quantity=max(1, int(item.get('quantity', 1))),
                price=item.get('price', float(t.price)),
                notes=(item.get('notes') or '').strip(),
            )

        rec.refresh_from_db()
        rec = MedicalRecord.objects.select_related('patient', 'doctor', 'appointment').prefetch_related('treatment_items__treatment').get(id=rec.id)
        return JsonResponse({'record': _medical_record_to_dict(rec)}, status=201)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_medical_record_detail(request, record_id):
    user, err = _require_admin(request)
    if err:
        return err

    from medical_records.models import MedicalRecord, MedicalRecordTreatment

    try:
        rec = MedicalRecord.objects.select_related('patient', 'doctor', 'appointment').prefetch_related('treatment_items__treatment').get(id=record_id)
    except MedicalRecord.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'record': _medical_record_to_dict(rec)})

    if request.method == 'PUT':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        if 'chief_complaint' in payload:
            rec.chief_complaint = (payload['chief_complaint'] or '').strip()
        if 'current_illness' in payload:
            rec.current_illness = (payload['current_illness'] or '').strip()
        if 'personal_history' in payload:
            rec.personal_history = (payload['personal_history'] or '').strip()
        if 'surgical_history' in payload:
            rec.surgical_history = (payload['surgical_history'] or '').strip()
        if 'allergic_history' in payload:
            rec.allergic_history = (payload['allergic_history'] or '').strip()
        if 'pharmacological_history' in payload:
            rec.pharmacological_history = (payload['pharmacological_history'] or '').strip()
        if 'family_history' in payload:
            rec.family_history = (payload['family_history'] or '').strip()
        if 'physical_exam' in payload:
            rec.physical_exam = (payload['physical_exam'] or '').strip()
        if 'diagnosis' in payload:
            rec.diagnosis = (payload['diagnosis'] or '').strip()
        if 'treatment_plan' in payload:
            rec.treatment_plan = (payload['treatment_plan'] or '').strip()
        if 'evolution' in payload:
            rec.evolution = (payload['evolution'] or '').strip()
        if 'informed_consent' in payload:
            rec.informed_consent = (payload['informed_consent'] or '').strip()
        if 'consent_signed' in payload:
            rec.consent_signed = bool(payload['consent_signed'])
        if 'notes' in payload:
            rec.notes = (payload['notes'] or '').strip()
        rec.save()

        if 'treatment_items' in payload:
            rec.treatment_items.all().delete()
            for item in payload['treatment_items']:
                tid = item.get('treatment_id')
                if not tid:
                    continue
                try:
                    t = Treatment.objects.get(id=tid)
                except Treatment.DoesNotExist:
                    continue
                MedicalRecordTreatment.objects.create(
                    medical_record=rec,
                    treatment=t,
                    quantity=max(1, int(item.get('quantity', 1))),
                    price=item.get('price', float(t.price)),
                    notes=(item.get('notes') or '').strip(),
                )

        rec = MedicalRecord.objects.select_related('patient', 'doctor', 'appointment').prefetch_related('treatment_items__treatment').get(id=record_id)
        return JsonResponse({'record': _medical_record_to_dict(rec)})

    if request.method == 'DELETE':
        rec.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)
