import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from landing.models import ClinicLanding
from treatments.models import Treatment
from .auth_views import get_auth_user


def _require_admin(request):
    """Return (user, error_response). If error_response is not None, return it."""
    user = get_auth_user(request)
    if user is None:
        return None, JsonResponse({'detail': 'Not authenticated'}, status=401)
    if user.role not in ('ADMIN',):
        return None, JsonResponse({'detail': 'Forbidden'}, status=403)
    if user.clinic is None:
        return None, JsonResponse({'detail': 'No clinic assigned'}, status=400)
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

    landing, _ = ClinicLanding.objects.get_or_create(clinic=user.clinic)

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
        qs = Treatment.objects.filter(clinic=user.clinic).order_by('category', 'name')
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
            clinic=user.clinic,
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
        t = Treatment.objects.get(id=treatment_id, clinic=user.clinic)
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
