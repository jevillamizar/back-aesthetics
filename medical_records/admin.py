from django.contrib import admin

from .models import Consent, MedicalRecord, MedicalRecordTreatment


class MedicalRecordTreatmentInline(admin.TabularInline):
    model = MedicalRecordTreatment
    extra = 0


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('patient', 'doctor', 'created_at')
    list_filter = ('doctor',)
    search_fields = ('patient__first_name', 'patient__last_name', 'doctor__email', 'diagnosis')
    inlines = (MedicalRecordTreatmentInline,)


@admin.register(MedicalRecordTreatment)
class MedicalRecordTreatmentAdmin(admin.ModelAdmin):
    list_display = ('medical_record', 'treatment', 'quantity', 'price', 'created_at')
    list_filter = ('treatment',)
    search_fields = ('medical_record__patient__first_name', 'medical_record__patient__last_name', 'treatment__name')


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'doctor', 'procedure_description', 'signed_by_name', 'signed_at', 'created_at')
    list_filter = ('doctor',)
    search_fields = ('patient__first_name', 'patient__last_name', 'doctor__email', 'signed_by_name', 'procedure_description')
    readonly_fields = ('created_at', 'updated_at')
