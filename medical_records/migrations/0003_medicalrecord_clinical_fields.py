from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='medicalrecord',
            name='current_illness',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='personal_history',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='surgical_history',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='allergic_history',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='pharmacological_history',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='family_history',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='physical_exam',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='treatment_plan',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='evolution',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='informed_consent',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='medicalrecord',
            name='consent_signed',
            field=models.BooleanField(default=False),
        ),
    ]
