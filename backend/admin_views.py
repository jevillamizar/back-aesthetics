import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt

from appointments.models import Appointment, Payment
from landing.models import ClinicLanding
from leads.models import Lead
from medical_records.models import Consent, MedicalRecord
from patients.models import Patient
from treatments.models import Treatment
from users.models import User
from .auth_views import get_auth_user


BUFFER_MINUTES = 5

# Límite de tamaño para signature_image (base64 data URL): 200 KB
MAX_SIGNATURE_IMAGE_BYTES = 200_000


def _validate_signature_image_size(payload: dict) -> JsonResponse | None:
    """Retorna JsonResponse 400 si signature_image excede el límite, o None si es válida."""
    sig = payload.get('signature_image') or ''
    if len(sig) > MAX_SIGNATURE_IMAGE_BYTES:
        return JsonResponse(
            {'detail': f'signature_image excede el tamaño máximo permitido ({MAX_SIGNATURE_IMAGE_BYTES // 1000} KB).'},
            status=400,
        )
    return None


# ─── Status transition rules ────────────────────────────────────────

ALLOWED_TRANSITIONS = {
    # Nuevo flujo simplificado
    # Valoración:   PENDING → COMPLETED (asistida) | NO_SHOW
    # Procedimiento: PENDING → IN_PROGRESS (atendida) | NO_SHOW
    #               IN_PROGRESS → COMPLETED
    Appointment.Status.PENDING:     {
        Appointment.Status.COMPLETED,
        Appointment.Status.IN_PROGRESS,
        Appointment.Status.NO_SHOW,
        Appointment.Status.CANCELED,
    },
    Appointment.Status.IN_PROGRESS: {Appointment.Status.COMPLETED, Appointment.Status.CANCELED},
    Appointment.Status.COMPLETED:   set(),
    Appointment.Status.CANCELED:    set(),
    Appointment.Status.NO_SHOW:     set(),
    Appointment.Status.EXPIRED:     set(),
}


def _require_admin(request):
    """Return (user, error_response). If error_response is not None, return it."""
    user = get_auth_user(request)
    if user is None:
        return None, JsonResponse({'detail': 'Not authenticated'}, status=401)
    if user.role not in ('ADMIN',):
        return None, JsonResponse({'detail': 'Forbidden'}, status=403)
    return user, None


def _require_staff(request):
    """Like _require_admin but also accepts DOCTOR role."""
    user = get_auth_user(request)
    if user is None:
        return None, JsonResponse({'detail': 'Not authenticated'}, status=401)
    if user.role not in ('ADMIN', 'DOCTOR'):
        return None, JsonResponse({'detail': 'Forbidden'}, status=403)
    return user, None


# ─── Profile ────────────────────────────────────────────────────────

@csrf_exempt
def admin_profile(request):
    """GET/PUT /api/profile/ — read or update the logged-in admin's own data."""
    user, err = _require_staff(request)
    if err:
        return err

    if request.method == 'GET':
        return JsonResponse({'profile': {
            'id': user.pk,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': user.phone,
            'document_type': user.document_type,
            'document_number': user.document_number,
            'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
            'role': user.role,
        }})

    if request.method == 'PUT':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        for f in ('first_name', 'last_name', 'phone', 'document_number'):
            if f in payload:
                setattr(user, f, (payload[f] or '').strip())
        if 'document_type' in payload:
            user.document_type = (payload['document_type'] or 'CC').strip()
        if 'date_of_birth' in payload:
            user.date_of_birth = payload['date_of_birth'] or None
        if 'email' in payload:
            new_email = (payload['email'] or '').strip()
            if new_email and new_email != user.email:
                if User.objects.filter(email=new_email).exists():
                    return JsonResponse({'detail': 'El correo ya está en uso.'}, status=400)
                user.email = new_email
        if payload.get('new_password'):
            if not payload.get('current_password'):
                return JsonResponse({'detail': 'Debes ingresar tu contraseña actual.'}, status=400)
            if not user.check_password(payload['current_password']):
                return JsonResponse({'detail': 'Contraseña actual incorrecta.'}, status=400)
            user.set_password(payload['new_password'].strip())
        user.save()
        return JsonResponse({'profile': {
            'id': user.pk,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': user.phone,
            'document_type': user.document_type,
            'document_number': user.document_number,
            'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
            'role': user.role,
        }})

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_clinic(request):
    """GET/PUT /api/clinic/ — clinic and landing data.

    GET: accesible para ADMIN y DOCTOR (lectura de configuración).
    PUT/POST: solo ADMIN (modificación de datos).
    """
    if request.method == 'GET':
        user, err = _require_staff(request)
    else:
        user, err = _require_admin(request)
    if err:
        return err

    landing, _ = ClinicLanding.objects.get_or_create(defaults={})

    # Fields from ClinicLanding model (contact & social)
    LANDING_FIELDS = ['phone', 'email', 'address',
                      'instagram_url', 'facebook_url']

    # Fields from Clinic model (business info) - logo handled separately
    CLINIC_TEXT_FIELDS = ['name', 'business_name', 'tax_id', 'company_type',
                          'short_description', 'whatsapp', 'city', 'country']

    from clinics.models import Clinic as _Clinic

    def _clinic_logo_url(clinic):
        if clinic and getattr(clinic, 'logo', None):
            try:
                return request.build_absolute_uri(clinic.logo.url)
            except Exception:
                pass
        return ''

    def _clinic_response(clinic):
        return JsonResponse({'clinic': {
            'logo_url': _clinic_logo_url(clinic),
            **{f: getattr(clinic, f, '') or '' for f in CLINIC_TEXT_FIELDS if clinic},
            **{f: getattr(landing, f, '') or '' for f in LANDING_FIELDS},
            'enable_medical_history': getattr(clinic, 'enable_medical_history', True) if clinic else True,
            'enable_consent': getattr(clinic, 'enable_consent', True) if clinic else True,
        }})

    clinic = getattr(request, 'tenant', None) or _Clinic.objects.first()

    if request.method == 'GET':
        return _clinic_response(clinic)

    if request.method in ('PUT', 'POST'):
        if request.content_type and 'multipart' in request.content_type.lower():
            from django.http.multipartparser import MultiPartParser
            _post, _files = MultiPartParser(
                request.META, request, request.upload_handlers, request.encoding
            ).parse()
            data = _post
            logo_file = _files.get('logo')
        else:
            try:
                data = json.loads(request.body.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                return JsonResponse({'detail': 'Invalid JSON'}, status=400)
            logo_file = None

        if clinic:
            for f in CLINIC_TEXT_FIELDS:
                if f in data:
                    setattr(clinic, f, (data[f] or '').strip())
            if logo_file:
                clinic.logo = logo_file
            if 'enable_medical_history' in data:
                clinic.enable_medical_history = str(data['enable_medical_history']).lower() not in ('false', '0', '')
            if 'enable_consent' in data:
                clinic.enable_consent = str(data['enable_consent']).lower() not in ('false', '0', '')
            if not clinic.enable_medical_history:
                clinic.enable_consent = False
            clinic.save()

        for f in LANDING_FIELDS:
            if f in data:
                setattr(landing, f, (data[f] or '').strip())
        landing.save()

        clinic = getattr(request, 'tenant', None) or _Clinic.objects.first()
        return _clinic_response(clinic)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Doctor scheduling helpers ──────────────────────────────────────

def check_doctor_conflict(doctor_id, starts_at, ends_at, exclude_appt_id=None):
    """Return the first conflicting appointment or None.

    A conflict exists when a doctor's existing appointment (not canceled/no-show)
    overlaps with [starts_at, ends_at] considering a 5-minute buffer on each side.
    """
    buf = timedelta(minutes=BUFFER_MINUTES)
    qs = (
        Appointment.objects
        .filter(doctor_id=doctor_id)
        .exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.NO_SHOW])
        .filter(
            starts_at__lt=ends_at + buf,
            ends_at__gt=starts_at - buf,
        )
    )
    if exclude_appt_id:
        qs = qs.exclude(id=exclude_appt_id)
    return qs.select_related('patient').first()


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
    'hero_image_urls', 'about_image_urls',
]

LANDING_BOOL_FIELDS = ['is_published', 'show_name', 'show_logo']

LANDING_IMAGE_FIELDS = ['hero_image', 'about_image']

# Campos URL que requieren validación de protocolos seguros
LANDING_URL_FIELDS = ['booking_url', 'instagram_url', 'facebook_url']

# Campos de color que requieren validación estricta
LANDING_COLOR_FIELDS = ['primary_color', 'secondary_color', 'accent_color', 'background_color', 'text_color']

# Campos de fuente que requieren validación contra Google Fonts
LANDING_FONT_FIELDS = ['font_heading', 'font_body', 'font_accent']

# Campos de contacto que requieren validación de formato
LANDING_CONTACT_FIELDS = ['phone', 'whatsapp_phone']

# Patrón regex para validar teléfonos (acepta +, espacios, guiones, paréntesis)
_PHONE_REGEX = r'^[\d\s\-\+\(\)]{7,20}$'

# Lista blanca de Google Fonts populares (subset de fuentes seguras)
# Fuente: https://fonts.google.com/
_GOOGLE_FONTS_WHITELIST = {
    # Serif fonts
    'playfair display', 'cormorant garamond', 'cormorant', 'eb garamond',
    'libre baskerville', 'merriweather', 'lora', 'crimson text',
    'source serif pro', 'pt serif', 'noto serif', 'roboto slab',
    'cardo', 'literata', 'newsreader', 'sorts mill goudy',
    
    # Sans-serif fonts
    'inter', 'roboto', 'open sans', 'lato', 'montserrat', 'poppins',
    'raleway', 'nunito', 'nunito sans', 'work sans', 'source sans pro',
    'pt sans', 'noto sans', 'fira sans', 'ibm plex sans', 'rubik',
    'barlow', 'manrope', 'space grotesk', 'sora', 'outfit',
    
    # Display/Decorative fonts
    'bebas neue', 'oswald', 'space mono', ' DM Sans', 'jetbrains mono',
    'fira code', 'inconsolata', 'cousine', 'anonymous pro',
    
    # Handwriting fonts
    'dancing script', 'great vibes', 'sacramento', 'parisienne',
    'allura', 'alex brush', 'pinyon script', 'tangerine',
}

# Protocolos permitidos para URLs de redes sociales
_ALLOWED_URL_SCHEMES = {'http', 'https'}
_BLOCKED_URL_SCHEMES = {'javascript', 'data', 'vbscript', 'file', 'about', 'blob', 'ftp', 'ftps'}


# Schemas de validación para campos JSON
# Cada schema define: tipo requerido, campos obligatorios, validación adicional
LANDING_JSON_SCHEMAS = {
    'trust_indicators': {
        'type': list,
        'max_items': 6,  # Límite máximo de 6 indicators
        'item_schema': {
            'type': dict,
            'required': ['icon', 'label', 'sub'],
            'fields': {
                'icon': {'type': str},
                'label': {'type': str},
                'sub': {'type': str},
            }
        }
    },
    'testimonials': {
        'type': list,
        'item_schema': {
            'type': dict,
            'required': ['name', 'treatment', 'rating', 'quote'],
            'fields': {
                'name': {'type': str},
                'treatment': {'type': str},
                'rating': {'type': int, 'min': 1, 'max': 5},
                'quote': {'type': str},
                'avatar_url': {'type': str, 'optional': True},  # Opcional
            }
        }
    },
    'about_bullets': {
        'type': list,
        'item_schema': {
            'type': (str, dict),  # Puede ser string simple o objeto
            'object_schema': {
                'required': ['title'],
                'fields': {
                    'title': {'type': str},
                    'description': {'type': str, 'optional': True},
                    'image_url': {'type': str, 'optional': True},
                }
            }
        }
    },
    'hero_image_urls': {
        'type': list,
        'item_schema': {
            'type': str,
            'url_validation': True,
        },
        'no_duplicates': True,  # Rechazar URLs duplicadas
    },
    'about_image_urls': {
        'type': list,
        'item_schema': {
            'type': str,
            'url_validation': True,
        },
        'no_duplicates': True,  # Rechazar URLs duplicadas
    },
}


def _validate_url_safe(url):
    """Validar que URL es segura (HTTP/HTTPS, no javascript:, data:, etc)."""
    if not isinstance(url, str):
        return False
    url_lower = url.lower().strip()
    # Rechazar protocolos peligrosos
    dangerous_protocols = ('javascript:', 'data:', 'vbscript:', 'file:', 'about:')
    if url_lower.startswith(dangerous_protocols):
        return False
    # Debe tener esquema HTTP o HTTPS o ser path relativo
    if url_lower.startswith(('http://', 'https://', '/', './')):
        return True
    # Si no tiene esquema, verificar que no parezca peligrosa
    if ':' in url_lower.split('?')[0].split('#')[0]:
        # Tiene esquema desconocido
        return False
    return True


def _validate_safe_url(url):
    """
    Validar que una URL de campo social es segura.
    
    Retorna (is_valid: bool, error_message: str)
    """
    if not isinstance(url, str):
        return False, 'La URL debe ser una cadena de texto'
    
    url_stripped = url.strip()
    
    if not url_stripped:
        return True, None  # URL vacía es válida (campo opcional)
    
    url_lower = url_stripped.lower()
    
    # Verificar protocolos bloqueados explícitamente
    for scheme in _BLOCKED_URL_SCHEMES:
        if url_lower.startswith(f'{scheme}:'):
            return False, f'Protocolo "{scheme}:" no permitido por seguridad'
    
    # Si tiene ://, verificar que sea protocolo permitido
    if '://' in url_stripped:
        scheme = url_stripped.split('://')[0].lower()
        if scheme not in _ALLOWED_URL_SCHEMES:
            return False, f'Protocolo "{scheme}:" no permitido. Use http:// o https://'
    
    # Si no tiene esquema, asumir https (campo opcional puede dejarse vacío)
    # No validamos más para permitir URLs relativas o sin esquema
    
    return True, None


def _validate_phone(phone_value):
    """
    Validar formato de número telefónico.
    
    Retorna (is_valid: bool, error_message: str)
    """
    if not isinstance(phone_value, str):
        return False, 'El teléfono debe ser una cadena de texto'
    
    phone_stripped = phone_value.strip()
    
    if not phone_stripped:
        return True, None  # Vacío es válido (campo opcional)
    
    # Verificar caracteres permitidos: dígitos, espacios, +, -, (, )
    import re
    if not re.match(_PHONE_REGEX, phone_stripped):
        return False, 'Formato de teléfono inválido. Use solo números, espacios, +, -, ()'
    
    # Debe contener al menos algunos dígitos
    digits = re.sub(r'\D', '', phone_stripped)
    if len(digits) < 7:
        return False, 'El teléfono debe tener al menos 7 dígitos'
    
    return True, None


def _create_audit_logs(landing, user, old_values, payload):
    """
    Crear registros de auditoría para campos que cambiaron.
    
    Args:
        landing: Instancia de ClinicLanding modificada
        user: Usuario que realizó el cambio
        old_values: Dict con valores antiguos {field_name: old_value}
        payload: Dict con nuevos valores del request
    """
    from landing.models import LandingAuditLog
    
    for field_name, old_value in old_values.items():
        if field_name not in payload:
            continue
            
        new_value = payload[field_name]
        
        # Normalizar valores para comparación
        # Convertir a string para comparación consistente
        old_str = '' if old_value is None else str(old_value)
        new_str = '' if new_value is None else str(new_value)
        
        # Para campos JSON, serializar a JSON string
        if field_name in LANDING_JSON_FIELDS:
            import json
            old_str = json.dumps(old_value) if old_value is not None else '[]'
            if isinstance(new_value, (list, dict)):
                new_str = json.dumps(new_value)
        
        # Para booleanos, normalizar
        if field_name in LANDING_BOOL_FIELDS:
            old_str = str(bool(old_value)).lower()
            if isinstance(new_value, str):
                new_str = str(new_value.lower() in ('true', '1', 'yes')).lower()
            else:
                new_str = str(bool(new_value)).lower()
        
        # Solo crear log si hubo cambio real
        if old_str != new_str:
            LandingAuditLog.objects.create(
                landing=landing,
                changed_by=user,
                field_name=field_name,
                old_value=old_str[:500],  # Limitar tamaño
                new_value=new_str[:500]
            )


# Patrones regex para validación de colores CSS
_COLOR_PATTERNS = {
    'hex': r'^#([A-Fa-f0-9]{3,4}|[A-Fa-f0-9]{6}|[A-Fa-f0-9]{8})$',
    'rgb': r'^rgb\(\d{1,3},\s*\d{1,3},\s*\d{1,3}\)$',
    'rgba': r'^rgba\(\d{1,3},\s*\d{1,3},\s*\d{1,3},\s*(0|1|0?\.\d+)\)$',
    'hsl': r'^hsl\(\d{1,3},\s*\d{1,3}%?,\s*\d{1,3}%?\)$',
    'hsla': r'^hsla\(\d{1,3},\s*\d{1,3}%?,\s*\d{1,3}%?,\s*(0|1|0?\.\d+)\)$',
}

# Lista de nombres de colores CSS estándar (subset más comunes)
_CSS_COLOR_NAMES = {
    'transparent', 'inherit', 'initial', 'unset',
    'black', 'white', 'red', 'green', 'blue', 'yellow', 'cyan', 'magenta',
    'gray', 'grey', 'silver', 'maroon', 'olive', 'lime', 'aqua', 'teal',
    'navy', 'fuchsia', 'purple', 'orange', 'pink', 'brown', 'gold', 'ivory',
    'beige', 'wheat', 'tan', 'khaki', 'plum', 'violet', 'indigo', 'coral',
    'salmon', 'crimson', 'firebrick', 'tomato', 'orangered', 'gold',
    'khaki', 'lavender', 'thistle', 'orchid', 'mediumorchid', 'mediumpurple',
    'rebeccapurple', 'slateblue', 'darkslateblue', 'mediumslateblue',
    'lightgreen', 'limegreen', 'forestgreen', 'darkgreen', 'seagreen',
    'mediumseagreen', 'springgreen', 'lightseagreen', 'darkseagreen',
    'palegreen', 'lightcyan', 'darkcyan', 'cadetblue', 'steelblue',
    'lightsteelblue', 'deepskyblue', 'dodgerblue', 'cornflowerblue',
    'royalblue', 'midnightblue', 'slategray', 'lightslategray', 'dimgray',
    'darkgray', 'lightgray', 'gainsboro', 'whitesmoke', 'ghostwhite',
    'aliceblue', 'honeydew', 'mintcream', 'azure', 'snow', 'floralwhite',
    'seashell', 'oldlace', 'antiquewhite', 'blanchedalmond', 'bisque',
    'peachpuff', 'moccasin', 'papayawhip', 'lemonchiffon', 'lightyellow',
    'lightgoldenrodyellow', 'cornsilk', 'linen', 'mistyrose', 'lavenderblush',
}

# Caracteres peligrosos que indican inyección CSS
# NOTA: Los paréntesis () se permiten porque son necesarios para rgb(), rgba(), hsl(), hsla()
_DANGEROUS_COLOR_CHARS = {';', '{', '}', '<', '>', '"', "'", '\\', '`', '='}


def _validate_safe_color(color_value):
    """
    Validar que un valor de color CSS es seguro y no contiene inyección.
    
    Retorna (is_valid: bool, error_message: str)
    """
    if not isinstance(color_value, str):
        return False, 'El color debe ser una cadena de texto'
    
    color_stripped = color_value.strip()
    
    if not color_stripped:
        return True, None  # Vacío es válido (campo opcional)
    
    # Verificar caracteres peligrosos que indican inyección
    for char in _DANGEROUS_COLOR_CHARS:
        if char in color_stripped:
            return False, f'Carácter "{char}" no permitido en color (riesgo de inyección CSS)'
    
    # Verificar si es un nombre de color CSS válido
    color_lower = color_stripped.lower()
    if color_lower in _CSS_COLOR_NAMES:
        return True, None
    
    # Verificar patrones HEX
    import re
    if re.match(_COLOR_PATTERNS['hex'], color_stripped):
        return True, None
    
    # Verificar patrones RGB/RGBA
    if re.match(_COLOR_PATTERNS['rgb'], color_stripped):
        return True, None
    if re.match(_COLOR_PATTERNS['rgba'], color_stripped):
        return True, None
    
    # Verificar patrones HSL/HSLA
    if re.match(_COLOR_PATTERNS['hsl'], color_stripped):
        return True, None
    if re.match(_COLOR_PATTERNS['hsla'], color_stripped):
        return True, None
    
    # Si no coincide con ningún patrón válido, es inválido
    return False, (
        f'Formato de color "{color_stripped}" no válido. '
        f'Use HEX (#rgb, #rrggbb), RGB/RGBA, HSL/HSLA, o nombres CSS estándar.'
    )


def _validate_safe_font(font_value):
    """
    Validar que un nombre de fuente está en la lista blanca de Google Fonts.
    
    Retorna (is_valid: bool, error_message: str)
    """
    if not isinstance(font_value, str):
        return False, 'La fuente debe ser una cadena de texto'
    
    font_stripped = font_value.strip()
    
    if not font_stripped:
        return True, None  # Vacío es válido (campo opcional)
    
    # Verificar caracteres peligrosos que indican inyección
    dangerous_chars = {'<', '>', '"', "'", ';', '{', '}', '(', ')', '\\', '`', '$'}
    for char in dangerous_chars:
        if char in font_stripped:
            return False, f'Carácter "{char}" no permitido en nombre de fuente (riesgo de inyección)'
    
    # Verificar que no sea una URL (http://, https://, //)
    if '://' in font_stripped or font_stripped.startswith('//'):
        return False, 'URLs no permitidas en nombre de fuente'
    
    # Normalizar nombre de fuente para comparación
    # Reemplazar + por espacio (formato de URL de Google Fonts)
    font_normalized = font_stripped.replace('+', ' ').lower().strip()
    
    # Verificar si está en la lista blanca
    if font_normalized in _GOOGLE_FONTS_WHITELIST:
        return True, None
    
    # Si no está en la lista, rechazar
    return False, (
        f'Fuente "{font_stripped}" no está en la lista de Google Fonts permitidas. '
        f'Use una fuente válida de Google Fonts.'
    )


def _validate_json_schema(value, field_name, schema):
    """
    Validar que un valor JSON cumple con el schema definido.
    
    Retorna (is_valid, error_message)
    """
    # Validar tipo raíz
    expected_type = schema.get('type')
    if expected_type and not isinstance(value, expected_type):
        return False, f'{field_name} must be a {expected_type.__name__ if isinstance(expected_type, type) else " or ".join(t.__name__ for t in expected_type)}'
    
    # Si es lista, validar items
    if isinstance(value, list):
        # Validar límite máximo de items
        max_items = schema.get('max_items')
        if max_items and len(value) > max_items:
            return False, f'{field_name} must have at most {max_items} items (got {len(value)})'
        
        item_schema = schema.get('item_schema')
        if item_schema:
            for i, item in enumerate(value):
                item_type = item_schema.get('type')
                
                # Si item puede ser múltiples tipos
                if isinstance(item_type, tuple):
                    if not isinstance(item, item_type):
                        return False, f'{field_name}[{i}] must be one of types: {item_type}'
                    # Si es dict y tenemos object_schema, validarlo
                    if isinstance(item, dict) and 'object_schema' in item_schema:
                        obj_schema = item_schema['object_schema']
                        required = obj_schema.get('required', [])
                        fields = obj_schema.get('fields', {})
                        
                        for req_field in required:
                            if req_field not in item:
                                return False, f'{field_name}[{i}] missing required field: {req_field}'
                        
                        for field_name_item, field_schema in fields.items():
                            if field_name_item in item:
                                field_val = item[field_name_item]
                                expected = field_schema.get('type')
                                if expected and not isinstance(field_val, expected):
                                    return False, f'{field_name}[{i}].{field_name_item} must be {expected.__name__}'
                                
                                # Validación URL si aplica
                                if field_schema.get('url_validation') and field_val:
                                    if not _validate_url_safe(field_val):
                                        return False, f'{field_name}[{i}].{field_name_item} contains unsafe URL'
                
                # Si item debe ser dict específico
                elif item_type == dict:
                    if not isinstance(item, dict):
                        return False, f'{field_name}[{i}] must be an object'
                    
                    required = item_schema.get('required', [])
                    fields = item_schema.get('fields', {})
                    
                    # Validar campos requeridos
                    for req_field in required:
                        if req_field not in item:
                            return False, f'{field_name}[{i}] missing required field: {req_field}'
                    
                    # Validar tipos de campos
                    for field_name_item, field_schema in fields.items():
                        if field_name_item in item:
                            field_val = item[field_name_item]
                            expected = field_schema.get('type')
                            
                            if expected and not isinstance(field_val, expected):
                                return False, f'{field_name}[{i}].{field_name_item} must be {expected.__name__}'
                            
                            # Validar rangos numéricos
                            if isinstance(field_val, int):
                                if 'min' in field_schema and field_val < field_schema['min']:
                                    return False, f'{field_name}[{i}].{field_name_item} must be >= {field_schema["min"]}'
                                if 'max' in field_schema and field_val > field_schema['max']:
                                    return False, f'{field_name}[{i}].{field_name_item} must be <= {field_schema["max"]}'
                            
                            # Validación URL si aplica
                            if field_schema.get('url_validation') and field_val:
                                if not _validate_url_safe(field_val):
                                    return False, f'{field_name}[{i}].{field_name_item} contains unsafe URL'
                
                # Si item debe ser string (URLs)
                elif item_type == str:
                    if not isinstance(item, str):
                        return False, f'{field_name}[{i}] must be a string'
                    if item_schema.get('url_validation') and item:
                        if not _validate_url_safe(item):
                            return False, f'{field_name}[{i}] is not a safe URL'
        
        # Validar duplicados si el schema lo requiere
        if schema.get('no_duplicates') and isinstance(value, list):
            seen = set()
            for i, item in enumerate(value):
                if isinstance(item, str):
                    # Normalizar para comparación (case-insensitive)
                    normalized = item.lower().strip()
                    if normalized in seen:
                        return False, f'{field_name} contains duplicate URL: "{item}" at position {i}'
                    seen.add(normalized)
    
    return True, None


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
            from django.http.multipartparser import MultiPartParser
            _post, files = MultiPartParser(
                request.META, request, request.upload_handlers, request.encoding
            ).parse()
            payload = _post.dict()
        else:
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                return JsonResponse({'detail': 'Invalid JSON'}, status=400)
            files = {}
        
        # Capturar valores antiguos para auditoría
        all_fields = LANDING_TEXT_FIELDS + LANDING_JSON_FIELDS + LANDING_BOOL_FIELDS + LANDING_IMAGE_FIELDS
        old_values = {f: getattr(landing, f, None) for f in all_fields if f in payload}

        for f in LANDING_TEXT_FIELDS:
            if f in payload:
                val = payload[f]
                
                # Validación especial para campos URL
                if f in LANDING_URL_FIELDS and val:
                    is_valid, error_msg = _validate_safe_url(val)
                    if not is_valid:
                        return JsonResponse(
                            {'detail': f'URL inválida en {f}: {error_msg}'},
                            status=400
                        )
                
                # Validación especial para campos de color
                if f in LANDING_COLOR_FIELDS and val:
                    is_valid, error_msg = _validate_safe_color(val)
                    if not is_valid:
                        return JsonResponse(
                            {'detail': f'Color inválido en {f}: {error_msg}'},
                            status=400
                        )
                
                # Validación especial para campos de fuente
                if f in LANDING_FONT_FIELDS and val:
                    is_valid, error_msg = _validate_safe_font(val)
                    if not is_valid:
                        return JsonResponse(
                            {'detail': f'Fuente inválida en {f}: {error_msg}'},
                            status=400
                        )
                
                # Validación especial para campos de contacto
                if f in LANDING_CONTACT_FIELDS and val:
                    is_valid, error_msg = _validate_phone(val)
                    if not is_valid:
                        return JsonResponse(
                            {'detail': f'Teléfono inválido en {f}: {error_msg}'},
                            status=400
                        )
                
                setattr(landing, f, val)

        for f in LANDING_JSON_FIELDS:
            if f in payload:
                val = payload[f]
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except json.JSONDecodeError:
                        return JsonResponse({'detail': f'Invalid JSON for {f}'}, status=400)
                
                # Validar schema del campo JSON
                schema = LANDING_JSON_SCHEMAS.get(f)
                if schema:
                    is_valid, error_msg = _validate_json_schema(val, f, schema)
                    if not is_valid:
                        return JsonResponse({'detail': error_msg}, status=400)
                
                setattr(landing, f, val)

        for f in LANDING_BOOL_FIELDS:
            if f in payload:
                val = payload[f]
                if isinstance(val, str):
                    val = val.lower() in ('true', '1', 'yes')
                setattr(landing, f, bool(val))

        for f in LANDING_IMAGE_FIELDS:
            if f in files:
                # Eliminar imagen antigua si existe (evita acumulación en storage)
                old_file = getattr(landing, f, None)
                if old_file and old_file.name:
                    try:
                        from django.core.files.storage import default_storage
                        if default_storage.exists(old_file.name):
                            default_storage.delete(old_file.name)
                    except Exception:
                        # Si falla la eliminación, no bloquear el upload
                        pass
                
                setattr(landing, f, files[f])

        # Ejecutar save y auditoría en transacción atómica
        # Si algo falla, todo se revierte (incluyendo eliminación de archivos)
        with transaction.atomic():
            landing.save()
            
            # Crear registros de auditoría para campos que cambiaron
            _create_audit_logs(landing, user, old_values, payload)
        
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
        'requires_consent': t.requires_consent,
        'image_url': t.image_url or '',
        'long_description': t.long_description or '',
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
            return JsonResponse({'detail': 'JSON inválido'}, status=400)

        # Validaciones de campos obligatorios
        name = (payload.get('name') or '').strip()
        if not name:
            return JsonResponse({'detail': 'El nombre del procedimiento es obligatorio'}, status=400)

        category = (payload.get('category') or '').strip()
        if not category:
            return JsonResponse({'detail': 'Debe seleccionar una categoría.'}, status=400)

        raw_price = payload.get('price')
        if raw_price is None or raw_price == '':
            return JsonResponse({'detail': 'El procedimiento debe tener precio.'}, status=400)
        try:
            price = Decimal(str(raw_price))
        except Exception:
            return JsonResponse({'detail': 'El precio debe ser un número válido'}, status=400)

        # Generar slug automáticamente desde el nombre si no se proporciona
        slug_input = payload.get('slug', '').strip()
        slug = slug_input if slug_input else slugify(name)

        # Validar unicidad del slug
        if slug and Treatment.objects.filter(slug=slug).exists():
            return JsonResponse({'detail': 'Ya existe un tratamiento con este slug. Intenta con otro nombre.'}, status=400)

        t = Treatment.objects.create(
            name=name,
            slug=slug or None,
            category=category,
            description=payload.get('description', '').strip(),
            long_description=payload.get('long_description', '').strip(),
            duration_minutes=payload.get('duration_minutes') or 30,
            price=price,
            is_active=payload.get('is_active', True),
            requires_consent=bool(payload.get('requires_consent', False)),
            image_url=payload.get('image_url', '').strip(),
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

        for field in ('name', 'slug', 'category', 'description', 'long_description', 'image_url'):
            if field in payload:
                setattr(t, field, (payload[field] or '').strip())
        if 'duration_minutes' in payload:
            t.duration_minutes = payload['duration_minutes'] or 30
        if 'price' in payload:
            t.price = payload['price']
        if 'is_active' in payload:
            t.is_active = bool(payload['is_active'])
        if 'requires_consent' in payload:
            t.requires_consent = bool(payload['requires_consent'])
        t.save()
        return JsonResponse({'treatment': _treatment_to_dict(t)})

    if request.method == 'DELETE':
        t.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Dashboard ───────────────────────────────────────────────────────

@csrf_exempt
def admin_dashboard(request):
    user, err = _require_staff(request)
    if err:
        return err

    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    _auto_no_show()
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    doctor_filter = {}
    if user.role == 'DOCTOR':
        doctor_filter = {'doctor_id': user.pk}

    from django.db.models import Sum

    appointments_today = Appointment.objects.filter(
        starts_at__gte=today_start,
        starts_at__lte=today_end,
        **doctor_filter,
    ).exclude(status=Appointment.Status.CANCELED).count()

    appointments_month = Appointment.objects.filter(
        starts_at__gte=month_start,
        **doctor_filter,
    ).exclude(status=Appointment.Status.CANCELED).count()

    patients_total = Patient.objects.count()
    treatments_active = Treatment.objects.filter(is_active=True).count()

    # ── New stats ──────────────────────────────────────────────────────
    valoraciones_no_asistidas = Appointment.objects.filter(
        appointment_type=Appointment.AppointmentType.VALORACION,
        status=Appointment.Status.NO_SHOW,
        **doctor_filter,
    ).count()

    procedimientos_atendidos = Appointment.objects.filter(
        appointment_type=Appointment.AppointmentType.TRATAMIENTO,
        status=Appointment.Status.COMPLETED,
        **doctor_filter,
    ).count()

    procedimientos_pendientes = Appointment.objects.filter(
        appointment_type=Appointment.AppointmentType.TRATAMIENTO,
        starts_at__gte=today_start,
        starts_at__lte=today_end,
        **doctor_filter,
    ).exclude(
        status__in=[Appointment.Status.COMPLETED, Appointment.Status.CANCELED]
    ).count()

    ingresos_hoy = float(
        Payment.objects.filter(
            appointment__starts_at__gte=today_start,
            appointment__starts_at__lte=today_end,
            status__in=[Payment.Status.PAID, Payment.Status.PARTIAL],
        ).aggregate(t=Sum('amount'))['t'] or 0
    )

    # ── Today's appointments (full detail) ────────────────────────────
    today_appts_qs = (
        Appointment.objects
        .select_related('patient', 'treatment', 'doctor')
        .prefetch_related('payment')
        .filter(starts_at__gte=today_start, starts_at__lte=today_end, **doctor_filter)
        .order_by('starts_at')
    )

    today_appointments = []
    for a in today_appts_qs:
        pay = getattr(a, 'payment', None)
        today_appointments.append({
            'id': a.id,
            'starts_at': a.starts_at.isoformat(),
            'ends_at': a.ends_at.isoformat(),
            'status': a.status,
            'appointment_type': a.appointment_type,
            'treatment_name': a.treatment.name if a.treatment else ('Valoración' if a.appointment_type == 'VALORACION' else '—'),
            'patient_name': f"{a.patient.first_name} {a.patient.last_name}".strip() if a.patient else '—',
            'patient_id': a.patient_id,
            'notes': a.notes or '',
            'doctor_id': a.doctor_id,
            'doctor_name': (
                f"{a.doctor.first_name} {a.doctor.last_name}".strip() or a.doctor.email
            ) if a.doctor else '—',
            'payment_status': pay.status if pay else None,
            'payment_amount': float(pay.amount) if pay else None,
        })

    import calendar as _cal
    last_day = _cal.monthrange(now.year, now.month)[1]
    month_end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)

    upcoming = (
        Appointment.objects
        .select_related('patient', 'treatment', 'doctor')
        .filter(starts_at__gte=month_start, starts_at__lte=month_end, **doctor_filter)
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
            'valoraciones_no_asistidas': valoraciones_no_asistidas,
            'procedimientos_atendidos': procedimientos_atendidos,
            'procedimientos_pendientes': procedimientos_pendientes,
            'ingresos_hoy': ingresos_hoy,
        },
        'today_appointments': today_appointments,
        'upcoming_appointments': upcoming_list,
    })


# ─── Appointments ────────────────────────────────────────────────────

def _auto_no_show():
    """Auto-update statuses for overdue appointments."""
    from django.utils import timezone as _tz
    _now = _tz.now()
    active_statuses = [
        Appointment.Status.PENDING,
        Appointment.Status.IN_PROGRESS,
    ]
    # Valoraciones vencidas → NO_SHOW
    Appointment.objects.filter(
        ends_at__lt=_now,
        status__in=active_statuses,
        appointment_type=Appointment.AppointmentType.VALORACION,
    ).update(status=Appointment.Status.NO_SHOW)
    # Procedimientos vencidos → EXPIRED
    Appointment.objects.filter(
        ends_at__lt=_now,
        status__in=active_statuses,
        appointment_type=Appointment.AppointmentType.TRATAMIENTO,
    ).update(status=Appointment.Status.EXPIRED)


def _appointment_to_dict(a):
    try:
        p = a.payment
        payment = {
            'id': p.id,
            'amount': float(p.amount),
            'method': p.method,
            'status': p.status,
            'notes': p.notes or '',
            'paid_at': p.paid_at.isoformat() if p.paid_at else None,
        }
    except Exception:
        payment = None

    try:
        mr = a.medical_record
        medical_record_id = mr.id if mr else None
    except Exception:
        medical_record_id = None

    consent_info = None
    if medical_record_id:
        try:
            c = a.medical_record.consents.order_by('-created_at').first()
            if c:
                consent_info = {
                    'id': c.id,
                    'signed': bool(c.signed_at),
                    'signed_at': c.signed_at.isoformat() if c.signed_at else None,
                    'signed_by_name': c.signed_by_name or '',
                }
        except Exception:
            pass

    return {
        'id': a.id,
        'starts_at': a.starts_at.isoformat(),
        'ends_at': a.ends_at.isoformat(),
        'status': a.status,
        'appointment_type': a.appointment_type,
        'notes': a.notes or '',
        'patient_id': a.patient_id,
        'patient_name': f"{a.patient.first_name} {a.patient.last_name}".strip() if a.patient else '—',
        'patient_email': a.patient.email if a.patient else '',
        'patient_phone': a.patient.phone if a.patient else '',
        'treatment_id': a.treatment_id,
        'treatment_name': a.treatment.name if a.treatment else None,
        'treatment_price': float(a.treatment.price) if a.treatment else None,
        'treatment_requires_consent': a.treatment.requires_consent if a.treatment else None,
        'doctor_id': a.doctor_id,
        'doctor_name': (
            f"{a.doctor.first_name} {a.doctor.last_name}".strip() or a.doctor.email
            if a.doctor else None
        ),
        'doctor_email': a.doctor.email if a.doctor else None,
        'payment': payment,
        'medical_record_id': medical_record_id,
        'consent': consent_info,
    }


@csrf_exempt
def admin_appointments(request): 
    user, err = _require_staff(request)
    if err:
        return err

    if request.method == 'GET':
        _auto_no_show()
        qs = (
            Appointment.objects
            .select_related('patient', 'treatment', 'doctor')
            .prefetch_related('payment', 'medical_record__consents')
            .order_by('starts_at')
        )
        # DOCTOR users can only see their own appointments
        if user.role == 'DOCTOR':
            qs = qs.filter(doctor_id=user.pk)
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
                .prefetch_related('payment', 'medical_record__consents')
                .filter(status__in=['COMPLETED', 'CANCELED', 'NO_SHOW'])
                .order_by('-starts_at')
            )
            if user.role == 'DOCTOR':
                qs = qs.filter(doctor_id=user.pk)
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

        doctor = None
        if payload.get('doctor_id'):
            try:
                doctor = User.objects.get(id=payload['doctor_id'], role=User.Role.DOCTOR)
            except User.DoesNotExist:
                return JsonResponse({'detail': 'Doctor no encontrado'}, status=400)
            conflict = check_doctor_conflict(doctor.id, starts_at, ends_at)
            if conflict:
                return JsonResponse({
                    'detail': f'Conflicto de horario: el doctor ya tiene una cita ({conflict.patient}) de {conflict.starts_at.strftime("%H:%M")} a {conflict.ends_at.strftime("%H:%M")}.'
                }, status=409)

        raw_type = (payload.get('appointment_type') or '').upper()
        appt_type = (
            Appointment.AppointmentType.VALORACION
            if raw_type == 'VALORACION'
            else Appointment.AppointmentType.TRATAMIENTO
        )

        a = Appointment.objects.create(
            patient=patient,
            treatment=treatment,
            doctor=doctor,
            starts_at=starts_at,
            ends_at=ends_at,
            appointment_type=appt_type,
            status=payload.get('status') or Appointment.Status.PENDING,
            notes=(payload.get('notes') or '').strip(),
        )

        # Create Google Calendar event to block the time slot
        try:
            from gcal.service import create_event as _create_gcal_event
            if appt_type == Appointment.AppointmentType.VALORACION:
                summary = f"Valoración — {patient.first_name} {patient.last_name}"
            else:
                proc_name = treatment.name if treatment else 'Procedimiento'
                summary = f"{proc_name} — {patient.first_name} {patient.last_name}"
            description = (payload.get('notes') or '').strip()
            if doctor:
                description = f"Responsable: {doctor.first_name} {doctor.last_name}" + (f"\n{description}" if description else '')
            gcal_id = _create_gcal_event(starts_at, ends_at, summary, description)
            if gcal_id:
                a.google_event_id = gcal_id
                a.save(update_fields=['google_event_id'])
        except Exception:
            pass  # GCal not connected — cita se guarda igual

        a.refresh_from_db()
        a.patient = patient
        a.treatment = treatment
        a.doctor = doctor
        return JsonResponse({'appointment': _appointment_to_dict(a)}, status=201)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_appointment_detail(request, appointment_id):
    user, err = _require_staff(request)
    if err:
        return err

    try:
        a = Appointment.objects.select_related('patient', 'treatment', 'doctor').prefetch_related('payment', 'medical_record__consents').get(id=appointment_id)
    except Appointment.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)

    # DOCTOR can only access their own appointments
    if user.role == 'DOCTOR' and a.doctor_id != user.pk:
        return JsonResponse({'detail': 'Forbidden'}, status=403)

    if request.method == 'GET':
        return JsonResponse({'appointment': _appointment_to_dict(a)})

    if request.method == 'PATCH':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)
        new_status = payload.get('status')
        if not new_status:
            return JsonResponse({'detail': 'status required'}, status=400)

        # Validate transition
        allowed = ALLOWED_TRANSITIONS.get(a.status, set())
        if new_status not in allowed:
            return JsonResponse(
                {'detail': f'Transición no permitida: {a.status} → {new_status}. Permitidas: {", ".join(allowed) or "ninguna"}'},
                status=400,
            )

        # Accept optional doctor_id assignment
        if 'doctor_id' in payload and payload['doctor_id']:
            try:
                doctor = User.objects.get(id=payload['doctor_id'], role=User.Role.DOCTOR)
            except User.DoesNotExist:
                return JsonResponse({'detail': 'Doctor no encontrado'}, status=400)
            conflict = check_doctor_conflict(doctor.id, a.starts_at, a.ends_at, exclude_appt_id=a.id)
            if conflict:
                return JsonResponse({
                    'detail': f'Conflicto de horario: el doctor ya tiene una cita ({conflict.patient}) de {conflict.starts_at.strftime("%H:%M")} a {conflict.ends_at.strftime("%H:%M")}.'
                }, status=409)
            a.doctor = doctor

        # PENDING/SCHEDULED → IN_PROGRESS: auto-create MedicalRecord if missing
        if new_status == Appointment.Status.IN_PROGRESS:
            clinic = getattr(request, 'tenant', None)
            hc_enabled = getattr(clinic, 'enable_medical_history', True) if clinic else True
            if hc_enabled:
                try:
                    a.medical_record
                except MedicalRecord.DoesNotExist:
                    MedicalRecord.objects.create(
                        patient=a.patient,
                        doctor=a.doctor,
                        appointment=a,
                    )

        a.status = new_status
        a.save(update_fields=['status', 'doctor_id', 'updated_at'])
        a = Appointment.objects.select_related('patient', 'treatment', 'doctor').prefetch_related('payment', 'medical_record__consents').get(id=appointment_id)
        return JsonResponse({'appointment': _appointment_to_dict(a)})

    if request.method == 'PUT':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        LOCKED_STATUSES = {Appointment.Status.COMPLETED}
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
        if 'doctor_id' in payload:
            if payload['doctor_id']:
                try:
                    a.doctor = User.objects.get(id=payload['doctor_id'], role=User.Role.DOCTOR)
                except User.DoesNotExist:
                    return JsonResponse({'detail': 'Doctor no encontrado'}, status=400)
            else:
                a.doctor = None
        # Validate doctor conflict after all fields are set
        if a.doctor_id:
            conflict = check_doctor_conflict(a.doctor_id, a.starts_at, a.ends_at, exclude_appt_id=a.id)
            if conflict:
                return JsonResponse({
                    'detail': f'Conflicto de horario: el doctor ya tiene una cita ({conflict.patient}) de {conflict.starts_at.strftime("%H:%M")} a {conflict.ends_at.strftime("%H:%M")}.'
                }, status=409)
        a.save()
        a.refresh_from_db()
        a = Appointment.objects.select_related('patient', 'treatment', 'doctor').prefetch_related('payment', 'medical_record__consents').get(id=appointment_id)
        return JsonResponse({'appointment': _appointment_to_dict(a)})

    if request.method == 'DELETE':
        a.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Appointment Payment ─────────────────────────────────────────────

@csrf_exempt
def admin_appointment_payment(request, appointment_id):
    user, err = _require_staff(request)
    if err:
        return err

    try:
        a = Appointment.objects.get(id=appointment_id)
    except Appointment.DoesNotExist:
        return JsonResponse({'detail': 'Appointment not found'}, status=404)

    if request.method == 'GET':
        try:
            p = a.payment
            return JsonResponse({'payment': {
                'id': p.id,
                'amount': float(p.amount),
                'method': p.method,
                'status': p.status,
                'notes': p.notes or '',
                'paid_at': p.paid_at.isoformat() if p.paid_at else None,
            }})
        except Payment.DoesNotExist:
            return JsonResponse({'payment': None})

    if request.method in ('POST', 'PUT'):
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        amount = payload.get('amount')
        if amount is None:
            return JsonResponse({'detail': 'amount required'}, status=400)

        method = payload.get('method', Payment.Method.CASH)
        status = payload.get('status', Payment.Status.PAID)
        notes = (payload.get('notes') or '').strip()

        paid_at = None
        if status in (Payment.Status.PAID, Payment.Status.PARTIAL):
            if payload.get('paid_at'):
                from django.utils.dateparse import parse_datetime as _pdt
                paid_at = _pdt(payload['paid_at'])
            else:
                paid_at = timezone.now()

        payment, created = Payment.objects.update_or_create(
            appointment=a,
            defaults={
                'amount': amount,
                'method': method,
                'status': status,
                'notes': notes,
                'paid_at': paid_at,
            },
        )
        return JsonResponse({
            'payment': {
                'id': payment.id,
                'amount': float(payment.amount),
                'method': payment.method,
                'status': payment.status,
                'notes': payment.notes or '',
                'paid_at': payment.paid_at.isoformat() if payment.paid_at else None,
            }
        }, status=201 if created else 200)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Appointment Consent ─────────────────────────────────────────────

@csrf_exempt
def admin_appointment_consent(request, appointment_id):
    """Create/retrieve a consent tied to a specific appointment's patient."""
    user, err = _require_staff(request)
    if err:
        return err

    try:
        a = Appointment.objects.select_related('patient', 'doctor').get(id=appointment_id)
    except Appointment.DoesNotExist:
        return JsonResponse({'detail': 'Appointment not found'}, status=404)

    if request.method == 'GET':
        # Filtrar por medical_record de esta cita (no por patient global)
        try:
            mr = a.medical_record
        except MedicalRecord.DoesNotExist:
            return JsonResponse({'consents': []})
        consents = Consent.objects.filter(
            medical_record=mr,
        ).select_related('patient', 'doctor').order_by('-created_at')
        return JsonResponse({'consents': [_consent_to_dict(c) for c in consents]})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        sig_err = _validate_signature_image_size(payload)
        if sig_err:
            return sig_err

        signed_at = None
        if payload.get('signed_by_name'):
            signed_at = timezone.now()

        from users.models import User
        doctor = a.doctor
        if payload.get('doctor_id'):
            try:
                doctor = User.objects.get(id=payload['doctor_id'], role='DOCTOR')
            except User.DoesNotExist:
                pass

        medical_record = None
        try:
            medical_record = a.medical_record
        except MedicalRecord.DoesNotExist:
            pass

        # Idempotencia: si ya existe consent firmado para este medical_record, retornarlo
        if medical_record:
            existing = (
                Consent.objects
                .filter(medical_record=medical_record, signed_at__isnull=False)
                .select_related('patient', 'doctor')
                .first()
            )
            if existing:
                return JsonResponse({'consent': _consent_to_dict(existing)}, status=200)

        consent = Consent.objects.create(
            patient=a.patient,
            doctor=doctor,
            medical_record=medical_record,
            procedure_description=(payload.get('procedure_description') or '').strip(),
            risks=(payload.get('risks') or '').strip(),
            notes=(payload.get('notes') or '').strip(),
            signed_by_name=(payload.get('signed_by_name') or '').strip(),
            signed_at=signed_at,
            signature_image=(payload.get('signature_image') or '').strip(),
        )
        consent = Consent.objects.select_related('patient', 'doctor').get(id=consent.id)
        return JsonResponse({'consent': _consent_to_dict(consent)}, status=201)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


MR_TEXT_FIELDS = (
    'chief_complaint', 'current_illness', 'personal_history', 'surgical_history',
    'allergic_history', 'pharmacological_history', 'family_history',
    'physical_exam', 'diagnosis', 'treatment_plan', 'evolution',
    'informed_consent', 'notes',
)


@csrf_exempt
def admin_appointment_complete(request, appointment_id):
    """POST /api/appointments/:id/complete/ — Completa una cita atómicamente.

    Agrupa en una sola transacción:
      1. Actualizar MedicalRecord con los campos recibidos.
      2. Crear Consent (opcional, según configuración y tratamiento).
      3. Marcar la cita como COMPLETED.

    Si cualquier paso falla se hace rollback completo.

    Body JSON:
      {
        "medical_record": { ...campos del MR... },
        "consent": { "signed_by_name": ..., "signature_image": ..., ... }  // opcional
      }

    NOTA DE DEUDA TÉCNICA:
    Este endpoint reemplaza la orquestación secuencial que hacía el frontend
    (3 llamadas separadas: PUT MR → POST consent → PATCH status). Existe para
    garantizar atomicidad. Los endpoints individuales siguen disponibles para
    otros flujos (draft, edición parcial, etc.).
    """
    from django.db import transaction

    user, err = _require_staff(request)
    if err:
        return err

    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        a = Appointment.objects.select_related('patient', 'doctor', 'treatment').get(id=appointment_id)
    except Appointment.DoesNotExist:
        return JsonResponse({'detail': 'Appointment not found'}, status=404)

    # Verificar que la transición a COMPLETED es válida
    allowed = ALLOWED_TRANSITIONS.get(a.status, set())
    if Appointment.Status.COMPLETED not in allowed:
        return JsonResponse(
            {'detail': f'Transición no permitida: {a.status} → COMPLETED. Permitidas: {", ".join(allowed) or "ninguna"}'},
            status=400,
        )

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    mr_data = payload.get('medical_record') or {}
    consent_data = payload.get('consent')  # None si se omite

    # Validar signature_image si viene consent
    if consent_data:
        sig_err = _validate_signature_image_size(consent_data)
        if sig_err:
            return sig_err

    try:
        with transaction.atomic():
            # ── Paso 1: Actualizar MedicalRecord ──
            try:
                rec = a.medical_record
            except MedicalRecord.DoesNotExist:
                raise ValueError('La cita no tiene historia clínica asociada.')

            for field in MR_TEXT_FIELDS:
                if field in mr_data:
                    setattr(rec, field, (mr_data[field] or '').strip())
            if 'consent_signed' in mr_data:
                rec.consent_signed = bool(mr_data['consent_signed'])
            rec.save()

            # ── Paso 2: Crear Consent (si se proporcionó) ──
            if consent_data:
                signed_by_name = (consent_data.get('signed_by_name') or '').strip()
                if not signed_by_name:
                    raise ValueError('signed_by_name es obligatorio en el consentimiento.')

                # Idempotencia: si ya existe consent firmado para este MR, no crear duplicado
                existing_consent = (
                    Consent.objects
                    .filter(medical_record=rec, signed_at__isnull=False)
                    .first()
                )
                if not existing_consent:
                    Consent.objects.create(
                        patient=a.patient,
                        doctor=a.doctor,
                        medical_record=rec,
                        procedure_description=(consent_data.get('procedure_description') or '').strip(),
                        risks=(consent_data.get('risks') or '').strip(),
                        notes=(consent_data.get('notes') or '').strip(),
                        signed_by_name=signed_by_name,
                        signed_at=timezone.now(),
                        signature_image=(consent_data.get('signature_image') or '').strip(),
                    )

            # ── Paso 3: Marcar COMPLETED ──
            a.status = Appointment.Status.COMPLETED
            a.save(update_fields=['status', 'updated_at'])

    except ValueError as ve:
        return JsonResponse({'detail': str(ve)}, status=400)

    # Refrescar para respuesta
    a = Appointment.objects.select_related(
        'patient', 'treatment', 'doctor'
    ).prefetch_related('payment', 'medical_record__consents').get(id=appointment_id)
    return JsonResponse({'appointment': _appointment_to_dict(a)}, status=200)


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
    user, err = _require_staff(request)
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
            from django.http.multipartparser import MultiPartParser
            _post, files = MultiPartParser(
                request.META, request, request.upload_handlers, request.encoding
            ).parse()
            payload = _post.dict()
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
        from django.db import transaction
        from appointments.models import Appointment as _Appt
        from medical_records.models import MedicalRecord as _MR
        with transaction.atomic():
            _Appt.objects.filter(patient=p).delete()
            _MR.objects.filter(patient=p).delete()
            p.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Doctors (Users with role=DOCTOR) ────────────────────────────────

def _doctor_to_dict(u, request=None):
    photo_url = ''
    if getattr(u, 'photo', None):
        try:
            photo_url = request.build_absolute_uri(u.photo.url) if request else u.photo.url
        except Exception:
            photo_url = ''
    return {
        'id': u.id,
        'first_name': u.first_name or '',
        'last_name': u.last_name or '',
        'email': u.email,
        'is_active': u.is_active,
        'document_type': u.document_type or '',
        'document_number': u.document_number or '',
        'date_of_birth': u.date_of_birth.isoformat() if u.date_of_birth and not isinstance(u.date_of_birth, str) else (u.date_of_birth or ''),
        'phone': u.phone or '',
        'profession': u.profession or '',
        'specialty': u.specialty or '',
        'university': u.university or '',
        'graduation_year': u.graduation_year,
        'rethus_number': u.rethus_number or '',
        'rethus_status': u.rethus_status or 'ACTIVE',
        'certifying_entity': u.certifying_entity or '',
        'professional_seal': u.professional_seal or '',
        'notes': u.notes or '',
        'bio': u.bio or '',
        'photo_url': photo_url,
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
        return JsonResponse({'doctors': [_doctor_to_dict(u, request) for u in qs]})

    if request.method == 'POST':
        import secrets, string as _string
        is_multipart = request.content_type and 'multipart' in request.content_type
        if is_multipart:
            payload = request.POST
            get = lambda k, d='': (payload.get(k) or d).strip()
        else:
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                return JsonResponse({'detail': 'Invalid JSON'}, status=400)
            get = lambda k, d='': (payload.get(k) or d).strip() if isinstance(payload.get(k, d), str) else payload.get(k, d)
        email = get('email')
        if not email:
            return JsonResponse({'detail': 'email required'}, status=400)
        if _User.objects.filter(email=email).exists():
            return JsonResponse({'detail': 'Email already in use'}, status=400)
        bio_val = get('bio')
        if bio_val and len(bio_val) < 100:
            return JsonResponse({'detail': 'La bio debe tener al menos 100 caracteres'}, status=400)
        if bio_val and len(bio_val) > 500:
            return JsonResponse({'detail': 'La bio no puede superar los 500 caracteres'}, status=400)
        password = get('password')
        generated = False
        if not password:
            alphabet = _string.ascii_letters + _string.digits + '!@#$'
            password = ''.join(secrets.choice(alphabet) for _ in range(12))
            generated = True
        grad_year = payload.get('graduation_year') or None
        doc = _User.objects.create_user(
            email=email,
            password=password,
            first_name=get('first_name'),
            last_name=get('last_name'),
            role=_User.Role.DOCTOR,
            document_type=get('document_type') or 'CC',
            document_number=get('document_number'),
            date_of_birth=payload.get('date_of_birth') or None,
            phone=get('phone'),
            profession=get('profession'),
            specialty=get('specialty'),
            university=get('university'),
            graduation_year=grad_year,
            rethus_number=get('rethus_number'),
            rethus_status=get('rethus_status') or 'ACTIVE',
            certifying_entity=get('certifying_entity'),
            professional_seal=get('professional_seal'),
            notes=get('notes'),
            bio=bio_val,
        )
        if is_multipart and request.FILES.get('photo'):
            doc.photo = request.FILES['photo']
            doc.save()
        resp = {'doctor': _doctor_to_dict(doc, request)}
        if generated:
            resp['generated_password'] = password
        return JsonResponse(resp, status=201)

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
        return JsonResponse({'doctor': _doctor_to_dict(doc, request)})

    if request.method == 'PUT':
        is_multipart = request.content_type and 'multipart' in request.content_type
        if is_multipart:
            from django.http import QueryDict
            from django.http.multipartparser import MultiPartParser
            _post, _files = MultiPartParser(
                request.META, request, request.upload_handlers, request.encoding
            ).parse()
            payload = _post
            upload_files = _files
            get_str = lambda k: (payload.get(k) or '').strip()
        else:
            upload_files = {}
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                return JsonResponse({'detail': 'Invalid JSON'}, status=400)
            get_str = lambda k: (payload.get(k) or '').strip()
        simple_fields = [
            'first_name', 'last_name', 'document_number', 'phone',
            'profession', 'specialty', 'university', 'rethus_number',
            'rethus_status', 'certifying_entity', 'professional_seal', 'notes',
        ]
        for f in simple_fields:
            if f in payload:
                setattr(doc, f, get_str(f))
        if 'bio' in payload:
            bio_val = get_str('bio')
            if bio_val and len(bio_val) < 100:
                return JsonResponse({'detail': 'La bio debe tener al menos 100 caracteres'}, status=400)
            if bio_val and len(bio_val) > 500:
                return JsonResponse({'detail': 'La bio no puede superar los 500 caracteres'}, status=400)
            doc.bio = bio_val
        if 'document_type' in payload:
            doc.document_type = get_str('document_type') or 'CC'
        if 'date_of_birth' in payload:
            doc.date_of_birth = payload.get('date_of_birth') or None
        if 'graduation_year' in payload:
            doc.graduation_year = payload.get('graduation_year') or None
        if 'email' in payload:
            new_email = get_str('email')
            if new_email and new_email != doc.email:
                if _User.objects.filter(email=new_email).exists():
                    return JsonResponse({'detail': 'Email already in use'}, status=400)
                doc.email = new_email
        if 'is_active' in payload:
            doc.is_active = bool(payload.get('is_active'))
        if payload.get('password'):
            doc.set_password(get_str('password'))
        if upload_files.get('photo'):
            doc.photo = upload_files['photo']
        doc.save()
        return JsonResponse({'doctor': _doctor_to_dict(doc, request)})

    if request.method == 'DELETE':
        doc.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_doctor_availability(request, doctor_id):
    """GET /api/doctors/<id>/availability/?date=YYYY-MM-DD
    Returns appointments for this doctor on the given date."""
    user, err = _require_admin(request)
    if err:
        return err
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    from django.utils.dateparse import parse_date as _pd
    d = _pd(request.GET.get('date', ''))
    if not d:
        d = timezone.now().date()

    try:
        User.objects.get(id=doctor_id, role=User.Role.DOCTOR)
    except User.DoesNotExist:
        return JsonResponse({'detail': 'Doctor not found'}, status=404)

    appts = (
        Appointment.objects
        .filter(doctor_id=doctor_id, starts_at__date=d)
        .exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.NO_SHOW])
        .select_related('patient', 'treatment')
        .order_by('starts_at')
    )
    slots = []
    for a in appts:
        slots.append({
            'id': a.id,
            'starts_at': a.starts_at.isoformat(),
            'ends_at': a.ends_at.isoformat(),
            'status': a.status,
            'patient_name': f"{a.patient.first_name} {a.patient.last_name}".strip() if a.patient else '—',
            'treatment_name': a.treatment.name if a.treatment else None,
        })
    return JsonResponse({
        'date': d.isoformat(),
        'buffer_minutes': BUFFER_MINUTES,
        'appointments': slots,
    })


# ─── Revenue ──────────────────────────────────────────────────────────

@csrf_exempt
def admin_revenue(request):
    user, err = _require_admin(request)
    if err:
        return err
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    from django.db.models import Sum, Count, F
    from django.db.models.functions import TruncMonth

    year = request.GET.get('year')
    try:
        year = int(year) if year else timezone.now().year
    except ValueError:
        year = timezone.now().year

    # ── Primary source: Payment records (PAID + PARTIAL) ──
    pay_qs = Payment.objects.filter(
        appointment__starts_at__year=year,
        status__in=[Payment.Status.PAID, Payment.Status.PARTIAL],
    ).select_related('appointment__doctor', 'appointment__treatment')

    # Monthly breakdown from payments
    monthly_raw = (
        pay_qs
        .annotate(month=TruncMonth('appointment__starts_at'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )
    monthly_map = {row['month'].strftime('%Y-%m'): float(row['total'] or 0) for row in monthly_raw}
    monthly_full = [
        {'month': f'{year}-{m:02d}', 'total': monthly_map.get(f'{year}-{m:02d}', 0)}
        for m in range(1, 13)
    ]
    total_year = sum(r['total'] for r in monthly_full)

    # Payment method breakdown
    method_raw = (
        pay_qs
        .values('method')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    METHOD_LABELS = {'CASH': 'Efectivo', 'CARD': 'Tarjeta', 'TRANSFER': 'Transferencia', 'OTHER': 'Otro'}
    payment_methods = [
        {'method': r['method'], 'label': METHOD_LABELS.get(r['method'], r['method']),
         'total': float(r['total'] or 0), 'count': r['count']}
        for r in method_raw
    ]

    # Top doctors by payment amount
    top_doctors_raw = (
        pay_qs
        .values(
            first=F('appointment__doctor__first_name'),
            last=F('appointment__doctor__last_name'),
            email=F('appointment__doctor__email'),
        )
        .annotate(total=Sum('amount'))
        .order_by('-total')[:6]
    )
    top_doctors_list = [
        {'name': f"{r['first'] or ''} {r['last'] or ''}".strip() or r['email'] or 'Sin médico',
         'total': float(r['total'] or 0)}
        for r in top_doctors_raw
    ]

    # Top treatments: from appointment.treatment (quick) + HC items as fallback
    from medical_records.models import MedicalRecordTreatment
    from django.db.models import ExpressionWrapper, DecimalField as _Dec

    # Treatments linked directly via appointment.treatment
    treat_from_appt = (
        pay_qs
        .exclude(appointment__treatment__isnull=True)
        .values(name=F('appointment__treatment__name'))
        .annotate(total=Sum('amount'))
        .order_by('-total')[:8]
    )
    treat_map: dict[str, float] = {}
    for r in treat_from_appt:
        treat_map[r['name']] = treat_map.get(r['name'], 0) + float(r['total'] or 0)

    # Also aggregate from HC treatment items (completed appointments with payments)
    revenue_expr = ExpressionWrapper(
        F('price') * F('quantity'), output_field=_Dec(max_digits=14, decimal_places=2)
    )
    hc_treats = (
        MedicalRecordTreatment.objects
        .filter(medical_record__appointment__starts_at__year=year,
                medical_record__appointment__payment__status__in=[
                    Payment.Status.PAID, Payment.Status.PARTIAL])
        .values(name=F('treatment__name'))
        .annotate(total=Sum(revenue_expr))
        .order_by('-total')[:8]
    )
    for r in hc_treats:
        key = r['name'] or 'Sin nombre'
        treat_map[key] = treat_map.get(key, 0) + float(r['total'] or 0)

    top_treatments_list = sorted(
        [{'name': k, 'total': v} for k, v in treat_map.items()],
        key=lambda x: x['total'], reverse=True
    )[:8]

    # Completed appointments count
    completed_count = Appointment.objects.filter(
        starts_at__year=year,
        status=Appointment.Status.COMPLETED,
    ).count()

    # Pending payments (registered but not yet paid)
    pending_total = float(
        Payment.objects.filter(
            appointment__starts_at__year=year,
            status=Payment.Status.PENDING,
        ).aggregate(t=Sum('amount'))['t'] or 0
    )

    return JsonResponse({
        'year': year,
        'total': total_year,
        'pending': pending_total,
        'completed_appointments': completed_count,
        'avg_per_appointment': round(total_year / completed_count, 2) if completed_count else 0,
        'monthly': monthly_full,
        'top_treatments': top_treatments_list,
        'top_doctors': top_doctors_list,
        'payment_methods': payment_methods,
    })


# ─── Medical Records ──────────────────────────────────────────────────

def _medical_record_to_dict(rec, request=None):
    items = rec.treatment_items.select_related('treatment').all()
    def _abs(url):
        return request.build_absolute_uri(url) if (request and url) else url
    return {
        'id': rec.id,
        'patient_id': rec.patient_id,
        'patient_name': f"{rec.patient.first_name} {rec.patient.last_name}".strip() if rec.patient else '—',
        'doctor_id': rec.doctor_id,
        'doctor_name': f"{rec.doctor.first_name} {rec.doctor.last_name}".strip() or rec.doctor.email if rec.doctor else '—',
        'doctor_profession': rec.doctor.profession or '' if rec.doctor else '',
        'doctor_specialty': rec.doctor.specialty or '' if rec.doctor else '',
        'doctor_rethus_number': rec.doctor.rethus_number or '' if rec.doctor else '',
        'doctor_rethus_status': rec.doctor.rethus_status or '' if rec.doctor else '',
        'doctor_professional_seal': rec.doctor.professional_seal or '' if rec.doctor else '',
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
        'photo_before_url': _abs(rec.photo_before.url) if rec.photo_before else '',
        'photo_after_url':  _abs(rec.photo_after.url)  if rec.photo_after  else '',
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
    user, err = _require_staff(request)
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
        return JsonResponse({'records': [_medical_record_to_dict(r, request) for r in qs]})

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
        return JsonResponse({'record': _medical_record_to_dict(rec, request)}, status=201)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_medical_record_detail(request, record_id):
    user, err = _require_staff(request)
    if err:
        return err

    from medical_records.models import MedicalRecord, MedicalRecordTreatment

    try:
        rec = MedicalRecord.objects.select_related('patient', 'doctor', 'appointment').prefetch_related('treatment_items__treatment').get(id=record_id)
    except MedicalRecord.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'record': _medical_record_to_dict(rec, request)})

    if request.method == 'PUT':
        is_multipart = request.content_type and 'multipart' in request.content_type
        if is_multipart:
            from django.http.multipartparser import MultiPartParser
            _post, _files = MultiPartParser(
                request.META, request, request.upload_handlers, request.encoding
            ).parse()
            if _files.get('photo_before'):
                rec.photo_before = _files['photo_before']
            if _files.get('photo_after'):
                rec.photo_after = _files['photo_after']
            rec.save(update_fields=['photo_before', 'photo_after', 'updated_at'])
            rec = MedicalRecord.objects.select_related('patient', 'doctor', 'appointment').prefetch_related('treatment_items__treatment').get(id=record_id)
            return JsonResponse({'record': _medical_record_to_dict(rec, request)})

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
        return JsonResponse({'record': _medical_record_to_dict(rec, request)})

    if request.method == 'DELETE':
        rec.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Consents ──────────────────────────────────────────────────

def _consent_to_dict(c):
    return {
        'id': c.id,
        'patient_id': c.patient_id,
        'patient_name': f"{c.patient.first_name} {c.patient.last_name}".strip() if c.patient else '—',
        'doctor_id': c.doctor_id,
        'doctor_name': (
            f"{c.doctor.first_name} {c.doctor.last_name}".strip() or c.doctor.email
            if c.doctor else '—'
        ),
        'doctor_profession': c.doctor.profession or '' if c.doctor else '',
        'doctor_specialty': c.doctor.specialty or '' if c.doctor else '',
        'doctor_rethus_number': c.doctor.rethus_number or '' if c.doctor else '',
        'doctor_professional_seal': c.doctor.professional_seal or '' if c.doctor else '',
        'medical_record_id': c.medical_record_id,
        'procedure_description': c.procedure_description or '',
        'risks': c.risks or '',
        'notes': c.notes or '',
        'signed_by_name': c.signed_by_name or '',
        'signed_at': c.signed_at.isoformat() if c.signed_at else None,
        'signature_image': c.signature_image or '',
        'created_at': c.created_at.isoformat(),
    }


@csrf_exempt
def admin_consents(request):
    admin, err = _require_admin(request)
    if err:
        return err

    if request.method == 'GET':
        qs = (
            Consent.objects
            .select_related('patient', 'doctor')
            .order_by('-created_at')
        )
        patient_id = request.GET.get('patient_id')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        signed = request.GET.get('signed')
        if signed == '1':
            qs = qs.filter(signed_at__isnull=False)
        elif signed == '0':
            qs = qs.filter(signed_at__isnull=True)
        return JsonResponse({'consents': [_consent_to_dict(c) for c in qs]})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        patient_id = payload.get('patient_id')
        if not patient_id:
            return JsonResponse({'detail': 'patient_id required'}, status=400)
        try:
            patient = Patient.objects.get(id=patient_id)
        except Patient.DoesNotExist:
            return JsonResponse({'detail': 'Patient not found'}, status=404)

        from users.models import User
        doctor = None
        if payload.get('doctor_id'):
            try:
                doctor = User.objects.get(id=payload['doctor_id'], role='DOCTOR')
            except User.DoesNotExist:
                pass

        from medical_records.models import MedicalRecord
        medical_record = None
        if payload.get('medical_record_id'):
            try:
                medical_record = MedicalRecord.objects.get(id=payload['medical_record_id'])
            except MedicalRecord.DoesNotExist:
                pass

        sig_err = _validate_signature_image_size(payload)
        if sig_err:
            return sig_err

        signed_at = None
        if payload.get('signed_at'):
            from django.utils.dateparse import parse_datetime
            signed_at = parse_datetime(payload['signed_at'])

        consent = Consent.objects.create(
            patient=patient,
            doctor=doctor,
            medical_record=medical_record,
            procedure_description=(payload.get('procedure_description') or '').strip(),
            risks=(payload.get('risks') or '').strip(),
            notes=(payload.get('notes') or '').strip(),
            signed_by_name=(payload.get('signed_by_name') or '').strip(),
            signed_at=signed_at,
            signature_image=(payload.get('signature_image') or '').strip(),
        )
        consent = Consent.objects.select_related('patient', 'doctor').get(id=consent.id)
        return JsonResponse({'consent': _consent_to_dict(consent)}, status=201)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_consent_detail(request, consent_id):
    admin, err = _require_admin(request)
    if err:
        return err

    try:
        consent = Consent.objects.select_related('patient', 'doctor').get(id=consent_id)
    except Consent.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'consent': _consent_to_dict(consent)})

    if request.method == 'PUT':
        try:
            payload = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        from users.models import User
        if 'doctor_id' in payload:
            if payload['doctor_id']:
                try:
                    consent.doctor = User.objects.get(id=payload['doctor_id'], role='DOCTOR')
                except User.DoesNotExist:
                    consent.doctor = None
            else:
                consent.doctor = None

        from medical_records.models import MedicalRecord
        if 'medical_record_id' in payload:
            if payload['medical_record_id']:
                try:
                    consent.medical_record = MedicalRecord.objects.get(id=payload['medical_record_id'])
                except MedicalRecord.DoesNotExist:
                    consent.medical_record = None
            else:
                consent.medical_record = None

        sig_err = _validate_signature_image_size(payload)
        if sig_err:
            return sig_err

        for field in ('procedure_description', 'risks', 'notes', 'signed_by_name', 'signature_image'):
            if field in payload:
                setattr(consent, field, (payload[field] or '').strip())

        if 'signed_at' in payload:
            if payload['signed_at']:
                from django.utils.dateparse import parse_datetime
                consent.signed_at = parse_datetime(payload['signed_at'])
            else:
                consent.signed_at = None

        consent.save()
        consent.refresh_from_db()
        consent = Consent.objects.select_related('patient', 'doctor').get(id=consent_id)
        return JsonResponse({'consent': _consent_to_dict(consent)})

    if request.method == 'DELETE':
        consent.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Payments ────────────────────────────────────────────────────────

def _payment_to_dict(p):
    return {
        'id': p.id,
        'appointment_id': p.appointment_id,
        'amount': float(p.amount),
        'method': p.method,
        'status': p.status,
        'notes': p.notes or '',
        'paid_at': p.paid_at.isoformat() if p.paid_at else None,
        'created_at': p.created_at.isoformat(),
    }


@csrf_exempt
def admin_appointment_payment(request, appointment_id):
    """GET/POST/PUT the payment for a specific appointment."""
    admin, err = _require_staff(request)
    if err:
        return err

    try:
        appointment = Appointment.objects.get(id=appointment_id)
    except Appointment.DoesNotExist:
        return JsonResponse({'detail': 'Appointment not found'}, status=404)

    if request.method == 'GET':
        try:
            return JsonResponse({'payment': _payment_to_dict(appointment.payment)})
        except Payment.DoesNotExist:
            return JsonResponse({'payment': None})

    if request.method in ('POST', 'PUT'):
        try:
            payload = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        paid_at = None
        if payload.get('paid_at'):
            from django.utils.dateparse import parse_datetime
            paid_at = parse_datetime(payload['paid_at'])
        elif payload.get('status') == 'PAID' and not payload.get('paid_at'):
            paid_at = timezone.now()

        try:
            p = appointment.payment
            p.amount = payload.get('amount', p.amount)
            p.method = payload.get('method', p.method)
            p.status = payload.get('status', p.status)
            p.notes = (payload.get('notes') or p.notes or '').strip()
            if paid_at is not None:
                p.paid_at = paid_at
            p.save()
        except Payment.DoesNotExist:
            p = Payment.objects.create(
                appointment=appointment,
                amount=payload.get('amount', 0),
                method=payload.get('method', Payment.Method.CASH),
                status=payload.get('status', Payment.Status.PENDING),
                notes=(payload.get('notes') or '').strip(),
                paid_at=paid_at,
            )

        return JsonResponse({'payment': _payment_to_dict(p)})

    if request.method == 'DELETE':
        try:
            appointment.payment.delete()
        except Payment.DoesNotExist:
            pass
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Leads ──────────────────────────────────────────────────────────

@csrf_exempt
def admin_leads(request):
    user, err = _require_staff(request)
    if err:
        return err

    if request.method == 'GET':
        status_filter = request.GET.get('status', '')
        source_filter = request.GET.get('source', '')
        search        = (request.GET.get('search') or '').strip()

        qs = Lead.objects.select_related('appointment', 'patient').order_by('-created_at')

        if status_filter:
            qs = qs.filter(status=status_filter)
        if source_filter:
            qs = qs.filter(source=source_filter)
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )

        def _serialize(lead):
            appt = lead.appointment
            return {
                'id':             lead.id,
                'first_name':     lead.first_name,
                'last_name':      lead.last_name,
                'phone':          lead.phone,
                'email':          lead.email,
                'interest_notes': lead.interest_notes,
                'source':         lead.source,
                'status':         lead.status,
                'patient_id':     lead.patient_id,
                'appointment': (
                    None if appt is None else {
                        'id':       appt.id,
                        'starts_at': appt.starts_at.isoformat(),
                        'ends_at':   appt.ends_at.isoformat(),
                        'status':    appt.status,
                        'appointment_type': appt.appointment_type,
                    }
                ),
                'notes':      lead.notes,
                'created_at': lead.created_at.isoformat(),
                'updated_at': lead.updated_at.isoformat(),
            }

        return JsonResponse({'results': [_serialize(l) for l in qs]})

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


@csrf_exempt
def admin_lead_detail(request, lead_id):
    user, err = _require_staff(request)
    if err:
        return err

    try:
        lead = Lead.objects.select_related('appointment', 'patient').get(id=lead_id)
    except Lead.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)

    if request.method == 'GET':
        appt = lead.appointment
        return JsonResponse({
            'id':             lead.id,
            'first_name':     lead.first_name,
            'last_name':      lead.last_name,
            'phone':          lead.phone,
            'email':          lead.email,
            'interest_notes': lead.interest_notes,
            'source':         lead.source,
            'status':         lead.status,
            'patient_id':     lead.patient_id,
            'appointment': (
                None if appt is None else {
                    'id':               appt.id,
                    'starts_at':        appt.starts_at.isoformat(),
                    'ends_at':          appt.ends_at.isoformat(),
                    'status':           appt.status,
                    'appointment_type': appt.appointment_type,
                    'google_event_id':  appt.google_event_id,
                }
            ),
            'notes':      lead.notes,
            'created_at': lead.created_at.isoformat(),
            'updated_at': lead.updated_at.isoformat(),
        })

    if request.method == 'PATCH':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        allowed_status = {s.value for s in Lead.Status}
        new_status = payload.get('status')
        if new_status is not None:
            if new_status not in allowed_status:
                return JsonResponse({'detail': f'Invalid status. Choices: {allowed_status}'}, status=400)
            lead.status = new_status

        for field in ('notes', 'interest_notes', 'phone', 'email'):
            if field in payload:
                setattr(lead, field, (payload[field] or '').strip())

        lead.save()
        return JsonResponse({'detail': 'Updated', 'status': lead.status})

    if request.method == 'DELETE':
        lead.delete()
        return JsonResponse({'detail': 'Deleted'}, status=204)

    return JsonResponse({'detail': 'Method not allowed'}, status=405)


# ─── Generic image upload ────────────────────────────────────────────

# Rate limiting storage (en producción usar Redis)
# Estructura: {user_id: [(timestamp, size_bytes), ...]}
_upload_rate_limit_storage = {}

# Configuración de rate limiting
MAX_UPLOADS_PER_MINUTE = 5
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
RATE_LIMIT_WINDOW_SECONDS = 60


def _check_upload_rate_limit(user_id):
    """
    Verificar si el usuario ha excedido el rate limit de uploads.
    
    Retorna (allowed: bool, retry_after: int, current_count: int)
    """
    import time
    
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    
    # Obtener o inicializar historial del usuario
    user_uploads = _upload_rate_limit_storage.get(user_id, [])
    
    # Limpiar entradas antiguas (fuera de la ventana de tiempo)
    user_uploads = [(ts, size) for ts, size in user_uploads if ts > window_start]
    
    # Verificar límite
    if len(user_uploads) >= MAX_UPLOADS_PER_MINUTE:
        # Calcular cuándo se libera el siguiente slot
        oldest_in_window = min(ts for ts, _ in user_uploads)
        retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - oldest_in_window)) + 1
        return False, retry_after, len(user_uploads)
    
    return True, 0, len(user_uploads)


def _record_upload(user_id, file_size):
    """Registrar un upload exitoso en el rate limiter."""
    import time
    
    if user_id not in _upload_rate_limit_storage:
        _upload_rate_limit_storage[user_id] = []
    
    _upload_rate_limit_storage[user_id].append((time.time(), file_size))


@csrf_exempt
def admin_upload_image(request):
    user, err = _require_admin(request)
    if err:
        return err
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    import os
    import uuid
    import time
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile

    # Validar rate limiting
    user_id = user.id
    allowed, retry_after, current_count = _check_upload_rate_limit(user_id)
    
    if not allowed:
        return JsonResponse(
            {
                'detail': f'Rate limit exceeded. Maximum {MAX_UPLOADS_PER_MINUTE} uploads per minute.',
                'retry_after': retry_after,
                'limit': MAX_UPLOADS_PER_MINUTE,
                'window_seconds': RATE_LIMIT_WINDOW_SECONDS,
            },
            status=429
        )

    uploaded = request.FILES.get('file')
    if not uploaded:
        return JsonResponse({'detail': 'No file provided'}, status=400)
    
    # Validar tamaño de archivo
    file_size = uploaded.size
    if file_size > MAX_UPLOAD_SIZE_BYTES:
        return JsonResponse(
            {
                'detail': f'File too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB.',
                'max_size_mb': MAX_UPLOAD_SIZE_BYTES // (1024 * 1024),
                'file_size_mb': round(file_size / (1024 * 1024), 2),
            },
            status=413
        )

    ext = os.path.splitext(uploaded.name)[1].lower()
    allowed_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}
    if ext not in allowed_exts:
        return JsonResponse({'detail': 'Tipo de archivo no permitido'}, status=400)
    
    # Validación de contenido: verificar que sea una imagen válida
    # usando magic bytes y Pillow (si está disponible)
    file_content = uploaded.read()
    uploaded.seek(0)  # Reset para leer de nuevo si es necesario
    
    # Verificar magic bytes
    is_valid_image = _validate_image_magic_bytes(file_content, ext)
    
    if not is_valid_image:
        return JsonResponse(
            {
                'detail': 'Archivo no es una imagen válida. '
                         'El contenido no coincide con la extensión.',
                'detected_type': _detect_content_type(file_content),
            },
            status=400
        )
    
    # Validación adicional con Pillow si está disponible
    try:
        from PIL import Image
        from io import BytesIO
        
        img = Image.open(BytesIO(file_content))
        img.verify()  # Verifica que la imagen no esté corrupta
        
        # Re-verificar formato detectado vs extensión
        pil_format = img.format.lower() if img.format else None
        ext_to_format = {
            '.jpg': 'jpeg',
            '.jpeg': 'jpeg',
            '.png': 'png',
            '.gif': 'gif',
            '.webp': 'webp',
            '.svg': 'svg',
        }
        
        expected_format = ext_to_format.get(ext)
        if expected_format and pil_format and pil_format != expected_format:
            # La extensión no coincide con el formato real
            return JsonResponse(
                {
                    'detail': f'Formato de archivo inconsistente. '
                              f'Extensión: {ext}, formato detectado: .{pil_format}',
                },
                status=400
            )
    except Exception as e:
        # Si Pillow no puede abrir la imagen, es inválida
        # excepto SVG que Pillow no soporta nativamente
        if ext not in ('.svg',):
            return JsonResponse(
                {
                    'detail': f'Archivo de imagen corrupto o no soportado: {str(e)}',
                },
                status=400
            )
    
    # Validación especial para SVG (prevenir XXE y XSS)
    if ext == '.svg':
        svg_valid, svg_error = _validate_svg_content(file_content)
        if not svg_valid:
            return JsonResponse(
                {'detail': f'Archivo SVG inválido o potencialmente peligroso: {svg_error}'},
                status=400
            )

    filename = f'uploads/{uuid.uuid4().hex}{ext}'
    path = default_storage.save(filename, ContentFile(file_content))
    url = request.build_absolute_uri(default_storage.url(path))
    
    # Registrar upload exitoso para rate limiting
    _record_upload(user_id, file_size)

    return JsonResponse({'url': url})


def _validate_image_magic_bytes(content, ext):
    """
    Validar que los magic bytes del archivo coincidan con la extensión.
    Retorna True si es válido, False si no.
    """
    if len(content) < 12:
        return False
    
    # Magic bytes signatures
    signatures = {
        '.png': (content[:8] == b'\x89PNG\r\n\x1a\n'),
        '.jpg': (content[:3] == b'\xff\xd8\xff'),
        '.jpeg': (content[:3] == b'\xff\xd8\xff'),
        '.gif': (content[:6] == b'GIF87a' or content[:6] == b'GIF89a'),
        '.webp': (content[:4] == b'RIFF' and content[8:12] == b'WEBP'),
    }
    
    # SVG no tiene magic bytes estándar, verificamos el contenido
    if ext == '.svg':
        try:
            content_str = content[:1024].decode('utf-8', errors='ignore').lower()
            return '<svg' in content_str and 'xmlns' in content_str
        except:
            return False
    
    return signatures.get(ext, False)


def _detect_content_type(content):
    """Detectar el tipo de contenido basado en magic bytes."""
    if len(content) < 12:
        return 'unknown/too-short'
    
    if content[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if content[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if content[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'image/webp'
    if content[:2] == b'PK':
        return 'application/zip'  # Posible docx, xlsx, o jar
    if b'%PDF' in content[:1024]:
        return 'application/pdf'
    if b'<?php' in content[:1024] or b'<?=' in content[:1024]:
        return 'application/x-php'
    if b'<script' in content[:1024].lower() or b'javascript:' in content[:1024].lower():
        return 'text/html-with-script'
    if b'<?xml' in content[:1024]:
        return 'application/xml'
    
    return 'unknown/binary'


def _validate_svg_content(content):
    """
    Validar contenido SVG para prevenir XXE y XSS.
    
    Retorna (is_valid: bool, error_message: str)
    """
    try:
        content_str = content.decode('utf-8', errors='ignore')
        content_lower = content_str.lower()
        
        # Verificar que sea SVG válido
        if '<svg' not in content_lower or 'xmlns' not in content_lower:
            return False, 'No es un archivo SVG válido'
        
        # Rechazar DOCTYPE (previene XXE)
        if '<!doctype' in content_lower or '<!DOCTYPE' in content_str:
            return False, 'SVG con DOCTYPE no permitido (riesgo XXE)'
        
        # Rechazar entidades XML (XXE)
        if '<!entity' in content_lower:
            return False, 'Entidades XML no permitidas (riesgo XXE)'
        
        # Rechazar scripts (XSS)
        if '<script' in content_lower:
            return False, 'Scripts en SVG no permitidos (riesgo XSS)'
        
        # Rechazar event handlers on* (onclick, onload, etc)
        import re
        if re.search(r'\son\w+\s*=', content_str, re.IGNORECASE):
            return False, 'Event handlers en SVG no permitidos (riesgo XSS)'
        
        # Rechazar javascript: URLs
        if 'javascript:' in content_lower:
            return False, 'URLs javascript: no permitidas en SVG'
        
        return True, None
    except Exception as e:
        return False, f'Error validando SVG: {str(e)}'
