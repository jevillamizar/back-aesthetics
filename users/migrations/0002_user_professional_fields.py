from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='document_type',
            field=models.CharField(blank=True, choices=[('CC', 'Cédula de ciudadanía'), ('CE', 'Cédula de extranjería'), ('PP', 'Pasaporte'), ('TP', 'Tarjeta profesional')], default='CC', max_length=5),
        ),
        migrations.AddField(
            model_name='user',
            name='document_number',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='user',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='user',
            name='profession',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='user',
            name='specialty',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='user',
            name='university',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='user',
            name='graduation_year',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='rethus_number',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='user',
            name='rethus_status',
            field=models.CharField(blank=True, choices=[('ACTIVE', 'Activo'), ('SUSPENDED', 'Suspendido')], default='ACTIVE', max_length=15),
        ),
        migrations.AddField(
            model_name='user',
            name='certifying_entity',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='user',
            name='professional_seal',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='user',
            name='notes',
            field=models.TextField(blank=True),
        ),
    ]
