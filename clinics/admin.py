from django.contrib import admin

from .models import Clinic, Domain


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'schema_name', 'is_active', 'created_at')
    search_fields = ('name', 'slug', 'schema_name')
    list_filter = ('is_active',)
    readonly_fields = ('schema_name',)


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')
    search_fields = ('domain',)
    list_filter = ('is_primary',)
