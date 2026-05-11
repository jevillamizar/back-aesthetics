"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from .admin_views import (
    admin_clinic, admin_profile,
    admin_appointment_detail, admin_appointments,
    admin_appointment_payment, admin_appointment_consent,
    admin_consent_detail, admin_consents,
    admin_dashboard, admin_landing,
    admin_doctor_availability, admin_doctor_detail, admin_doctors,
    admin_lead_detail, admin_leads,
    admin_medical_record_detail, admin_medical_records,
    admin_patient_detail, admin_patients,
    admin_revenue,
    admin_treatment_detail, admin_treatments,
    admin_upload_image,
)
from gcal.views import gcal_connect, gcal_disconnect, gcal_oauth2callback, gcal_set_calendar, gcal_status

from .auth_views import auth_login, auth_me
from .views import (
    public_availability,
    public_create_appointment,
    public_create_lead,
    public_landing,
    public_team,
    public_treatments,
    tenant_debug,
)

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('tenant/', tenant_debug),
    path('public/appointments/', public_create_appointment),
    path('public/treatments/', public_treatments),
    path('public/landing/', public_landing),
    path('public/availability/', public_availability),
    path('public/leads/', public_create_lead),
    path('public/team/', public_team),
    path('api/gcal/connect/', gcal_connect),
    path('api/gcal/oauth2callback/', gcal_oauth2callback),
    path('api/gcal/status/', gcal_status),
    path('api/gcal/calendar/', gcal_set_calendar),
    path('api/gcal/disconnect/', gcal_disconnect),
    path('api/auth/login/', auth_login),
    path('api/auth/me/', auth_me),
    path('api/profile/', admin_profile),
    path('api/clinic/', admin_clinic),
    path('api/landing/', admin_landing),
    path('api/treatments/', admin_treatments),
    path('api/treatments/<int:treatment_id>/', admin_treatment_detail),
    path('api/dashboard/', admin_dashboard),
    path('api/appointments/', admin_appointments),
    path('api/appointments/<int:appointment_id>/', admin_appointment_detail),
    path('api/appointments/<int:appointment_id>/payment/', admin_appointment_payment),
    path('api/appointments/<int:appointment_id>/consent/', admin_appointment_consent),
    path('api/patients/', admin_patients),
    path('api/patients/<int:patient_id>/', admin_patient_detail),
    path('api/doctors/', admin_doctors),
    path('api/doctors/<int:doctor_id>/', admin_doctor_detail),
    path('api/doctors/<int:doctor_id>/availability/', admin_doctor_availability),
    path('api/revenue/', admin_revenue),
    path('api/upload-image/', admin_upload_image),
    path('api/leads/', admin_leads),
    path('api/leads/<int:lead_id>/', admin_lead_detail),
    path('api/medical-records/', admin_medical_records),
    path('api/medical-records/<int:record_id>/', admin_medical_record_detail),
    path('api/consents/', admin_consents),
    path('api/consents/<int:consent_id>/', admin_consent_detail),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
