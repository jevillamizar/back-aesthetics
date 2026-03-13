from django.contrib import admin

from .models import MedicalRecord, MedicalRecordTreatment


class MedicalRecordTreatmentInline(admin.TabularInline):
    model = MedicalRecordTreatment
    extra = 0


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('patient', 'doctor', 'clinic', 'created_at')
    list_filter = ('clinic', 'doctor')
    search_fields = ('patient__first_name', 'patient__last_name', 'doctor__email', 'diagnosis')
    inlines = (MedicalRecordTreatmentInline,)


@admin.register(MedicalRecordTreatment)
class MedicalRecordTreatmentAdmin(admin.ModelAdmin):
    list_display = ('medical_record', 'treatment', 'quantity', 'price', 'clinic', 'created_at')
    list_filter = ('clinic', 'treatment')
    search_fields = ('medical_record__patient__first_name', 'medical_record__patient__last_name', 'treatment__name')
