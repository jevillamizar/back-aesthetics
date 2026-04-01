"""
URL configuration for public schema (tenant management)
"""
from django.contrib import admin
from django.urls import path

from .auth_views import auth_login, auth_me

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/login/', auth_login),
    path('api/auth/me/', auth_me),
]
