from django.http import JsonResponse


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
