"""
OAuth2 views for connecting a clinic's Google Calendar.
These endpoints are protected — only authenticated clinic admins can initiate the flow.
"""
import datetime
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from backend.auth_views import get_auth_user

from .models import GoogleCalendarToken
from .service import get_oauth_flow


def _require_admin(request):
    user = get_auth_user(request)
    if user is None:
        return None, JsonResponse({'detail': 'Not authenticated'}, status=401)
    if user.role not in ('ADMIN',):
        return None, JsonResponse({'detail': 'Forbidden'}, status=403)
    return user, None


def gcal_connect(request):
    """Step 1: return the Google OAuth2 consent URL so the client can open it."""
    _, err = _require_admin(request)
    if err:
        return err

    flow = get_oauth_flow()
    auth_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true',
    )
    return JsonResponse({'auth_url': auth_url, 'state': state})


def gcal_oauth2callback(request):
    """Step 2: Google redirects here with the auth code."""
    code = request.GET.get('code')

    if not code:
        return JsonResponse({'detail': 'Missing code'}, status=400)

    flow = get_oauth_flow()
    flow.fetch_token(code=code)

    creds = flow.credentials

    expiry = None
    if creds.expiry:
        expiry = creds.expiry.replace(tzinfo=datetime.timezone.utc)

    token, _ = GoogleCalendarToken.objects.update_or_create(
        id=1,
        defaults={
            'access_token':  creds.token,
            'refresh_token': creds.refresh_token or '',
            'token_expiry':  expiry,
            'scopes':        ' '.join(creds.scopes or []),
        },
    )

    return JsonResponse({'detail': 'Google Calendar connected', 'calendar_id': token.calendar_id or 'primary'})


def gcal_status(request):
    """Returns whether a Google Calendar is connected for this tenant."""
    _, err = _require_admin(request)
    if err:
        return err

    token = GoogleCalendarToken.objects.first()
    if token is None:
        return JsonResponse({'connected': False})
    return JsonResponse({
        'connected': True,
        'calendar_id': token.calendar_id or 'primary',
        'connected_at': token.connected_at.isoformat(),
    })


@csrf_exempt
def gcal_set_calendar(request):
    """Updates the calendar_id to use (e.g. a specific shared calendar vs primary)."""
    _, err = _require_admin(request)
    if err:
        return err

    if request.method != 'PATCH':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    calendar_id = (payload.get('calendar_id') or '').strip()
    if not calendar_id:
        return JsonResponse({'detail': 'calendar_id is required'}, status=400)

    token = GoogleCalendarToken.objects.first()
    if token is None:
        return JsonResponse({'detail': 'No Google Calendar connected'}, status=404)

    token.calendar_id = calendar_id
    token.save(update_fields=['calendar_id', 'updated_at'])
    return JsonResponse({'detail': 'Calendar updated', 'calendar_id': calendar_id})


@csrf_exempt
def gcal_disconnect(request):
    """Removes the stored credentials."""
    _, err = _require_admin(request)
    if err:
        return err

    if request.method != 'DELETE':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    GoogleCalendarToken.objects.all().delete()
    return JsonResponse({'detail': 'Disconnected'})
