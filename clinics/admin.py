from django.contrib import admin
from django.utils.text import slugify

from .models import Clinic, Domain


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 1
    fields = ('domain', 'is_primary')
    verbose_name = 'Domain'
    verbose_name_plural = 'Domains'


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'schema_name', 'get_domains', 'is_active', 'created_at')
    search_fields = ('name', 'slug', 'schema_name')
    list_filter = ('is_active',)
    readonly_fields = ('schema_name',)
    inlines = [DomainInline]

    def get_domains(self, obj):
        return ', '.join(obj.domains.values_list('domain', flat=True))
    get_domains.short_description = 'Domains'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.schema_name = slugify(obj.slug).replace('-', '_')
        super().save_model(request, obj, form, change)


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')
    search_fields = ('domain',)
    list_filter = ('is_primary',)
