from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0003_medicalrecord_clinical_fields'),
        ('patients', '0004_patient_admin_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Consent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('procedure_description', models.TextField(blank=True)),
                ('risks', models.TextField(blank=True)),
                ('notes', models.TextField(blank=True)),
                ('signed_by_name', models.CharField(blank=True, max_length=255)),
                ('signed_at', models.DateTimeField(blank=True, null=True)),
                ('signature_image', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('doctor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='consents', to=settings.AUTH_USER_MODEL)),
                ('medical_record', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='consents', to='medical_records.medicalrecord')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='consents', to='patients.patient')),
            ],
            options={
                'verbose_name': 'Consent',
                'verbose_name_plural': 'Consents',
            },
        ),
        migrations.AddIndex(
            model_name='consent',
            index=models.Index(fields=['patient', 'created_at'], name='medical_rec_patient_consent_idx'),
        ),
    ]
