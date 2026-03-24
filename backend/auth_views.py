import json

from django.contrib.auth import authenticate
from django.core import signing
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from users.models import User


TOKEN_MAX_AGE = 60 * 60 * 24  # 24 hours


def _make_token(user: User) -> str:
    return signing.dumps({'uid': user.pk}, salt='auth-token')


def _user_from_token(token: str):
    try:
        data = signing.loads(token, salt='auth-token', max_age=TOKEN_MAX_AGE)
    except (signing.BadSignature, signing.SignatureExpired):
        return None
    try:
        return User.objects.select_related('clinic').get(pk=data['uid'], is_active=True)
    except User.DoesNotExist:
        return None


def get_auth_user(request):
    """Extract authenticated user from Authorization header."""
    header = (request.headers.get('Authorization') or '').strip()
    if not header.startswith('Bearer '):
        return None
    return _user_from_token(header[7:])


def _user_payload(user: User) -> dict:
    return {
        'id': user.pk,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'role': user.role,
        'clinic': {
            'id': user.clinic.id,
            'name': user.clinic.name,
            'slug': user.clinic.slug,
        } if user.clinic else None,
    }


@csrf_exempt
def auth_login(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    email = (body.get('email') or '').strip()
    password = (body.get('password') or '').strip()

    if not email or not password:
        return JsonResponse({'detail': 'email and password are required'}, status=400)

    user = authenticate(request, email=email, password=password)
    if user is None:
        return JsonResponse({'detail': 'Invalid credentials'}, status=401)

    if not user.is_active:
        return JsonResponse({'detail': 'Account disabled'}, status=403)

    return JsonResponse({
        'token': _make_token(user),
        'user': _user_payload(user),
    })


@csrf_exempt
def auth_me(request):
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    user = get_auth_user(request)
    if user is None:
        return JsonResponse({'detail': 'Not authenticated'}, status=401)

    return JsonResponse({'user': _user_payload(user)})
