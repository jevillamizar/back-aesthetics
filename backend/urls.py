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
    admin_appointment_detail, admin_appointments,
    admin_dashboard, admin_landing,
    admin_doctor_detail, admin_doctors,
    admin_patient_detail, admin_patients,
    admin_treatment_detail, admin_treatments,
)
from .auth_views import auth_login, auth_me
from .views import public_create_appointment, public_landing, public_treatments, tenant_debug

urlpatterns = [
    path('admin/', admin.site.urls),
    path('tenant/', tenant_debug),
    path('public/appointments/', public_create_appointment),
    path('public/treatments/', public_treatments),
    path('public/landing/', public_landing),
    path('api/auth/login/', auth_login),
    path('api/auth/me/', auth_me),
    path('api/landing/', admin_landing),
    path('api/treatments/', admin_treatments),
    path('api/treatments/<int:treatment_id>/', admin_treatment_detail),
    path('api/dashboard/', admin_dashboard),
    path('api/appointments/', admin_appointments),
    path('api/appointments/<int:appointment_id>/', admin_appointment_detail),
    path('api/patients/', admin_patients),
    path('api/patients/<int:patient_id>/', admin_patient_detail),
    path('api/doctors/', admin_doctors),
    path('api/doctors/<int:doctor_id>/', admin_doctor_detail),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
