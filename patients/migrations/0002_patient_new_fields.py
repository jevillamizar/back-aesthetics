from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='document_type',
            field=models.CharField(
                max_length=10,
                choices=[('CC','Cédula de Ciudadanía'),('CE','Cédula de Extranjería'),('TI','Tarjeta de Identidad'),('PP','Pasaporte'),('RC','Registro Civil'),('NIT','NIT')],
                blank=True,
                default='',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='patient',
            name='document_number',
            field=models.CharField(max_length=50, blank=True, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='patient',
            name='sex',
            field=models.CharField(
                max_length=1,
                choices=[('M','Masculino'),('F','Femenino'),('O','Otro')],
                blank=True,
                default='',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='patient',
            name='address',
            field=models.CharField(max_length=255, blank=True, default=''),
            preserve_default=False,
        ),
    ]
