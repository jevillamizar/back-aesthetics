from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0002_patient_new_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='photo',
            field=models.ImageField(upload_to='patients/photos/', null=True, blank=True),
        ),
    ]
