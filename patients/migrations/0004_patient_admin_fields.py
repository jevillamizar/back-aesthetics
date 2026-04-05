from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0003_patient_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='eps',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='patient',
            name='legal_guardian',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='patient',
            name='emergency_contact_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='patient',
            name='emergency_contact_phone',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='patient',
            name='emergency_contact_relation',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
