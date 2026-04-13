from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'role', 'profession', 'specialty', 'rethus_status', 'is_active')
    list_filter = ('role', 'rethus_status', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'document_number', 'rethus_number')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Datos personales', {'fields': ('first_name', 'last_name', 'role')}),
        ('Identificación', {'fields': ('document_type', 'document_number', 'date_of_birth', 'phone')}),
        ('Información profesional', {'fields': ('profession', 'specialty', 'university', 'graduation_year')}),
        ('Registro ReTHUS', {'fields': ('rethus_number', 'rethus_status', 'certifying_entity')}),
        ('Responsabilidad', {'fields': ('professional_seal', 'notes')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas importantes', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': (
            'email', 'password1', 'password2', 'first_name', 'last_name', 'role',
            'document_type', 'document_number', 'phone',
            'profession', 'specialty',
            'rethus_number', 'rethus_status',
            'is_staff', 'is_superuser',
        )}),
    )
