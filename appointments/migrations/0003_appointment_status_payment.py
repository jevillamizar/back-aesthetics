from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appointment',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING',     'Pendiente'),
                    ('SCHEDULED',   'Programada'),
                    ('IN_PROGRESS', 'En curso'),
                    ('COMPLETED',   'Completada'),
                    ('CANCELED',    'Cancelada'),
                    ('NO_SHOW',     'No asistió'),
                ],
                default='SCHEDULED',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('method', models.CharField(
                    choices=[('CASH', 'Efectivo'), ('CARD', 'Tarjeta'), ('TRANSFER', 'Transferencia'), ('OTHER', 'Otro')],
                    default='CASH', max_length=20,
                )),
                ('status', models.CharField(
                    choices=[('PENDING', 'Pendiente'), ('PAID', 'Pagado'), ('PARTIAL', 'Parcial'), ('REFUNDED', 'Reembolsado')],
                    default='PENDING', max_length=20,
                )),
                ('notes', models.TextField(blank=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('appointment', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='payment',
                    to='appointments.appointment',
                )),
            ],
            options={'verbose_name': 'Payment', 'verbose_name_plural': 'Payments'},
        ),
    ]
