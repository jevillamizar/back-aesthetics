"""
Comando para crear un usuario ADMIN en un tenant específico.

Uso:
  python manage.py create_tenant_admin \
    --tenant=demo_clinic \
    --email=admin@demo-clinic.com \
    --password=AestheticsDemo2026 \
    --first-name=Admin \
    --last-name=Principal
"""
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Crea un usuario ADMIN en el tenant especificado'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            required=True,
            help='Schema name del tenant (ej: demo_clinic)',
        )
        parser.add_argument(
            '--email',
            required=True,
            help='Email del administrador',
        )
        parser.add_argument(
            '--password',
            required=True,
            help='Contraseña inicial',
        )
        parser.add_argument(
            '--first-name',
            default='',
            help='Nombre (opcional)',
        )
        parser.add_argument(
            '--last-name',
            default='',
            help='Apellido (opcional)',
        )

    def handle(self, *args, **options):
        from users.models import User

        tenant_schema = options['tenant']
        email = options['email']

        # Verificar que el tenant existe (opcional, el schema_context fallará si no existe)
        with schema_context(tenant_schema):
            if User.objects.filter(email=email).exists():
                raise CommandError(
                    f'Ya existe un usuario con email {email} en el tenant {tenant_schema}'
                )

            user = User.objects.create_user(
                email=email,
                password=options['password'],
                role=User.Role.ADMIN,
                first_name=options.get('first_name', ''),
                last_name=options.get('last_name', ''),
                is_active=True,
                is_staff=True,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Admin {user.email} creado exitosamente en tenant {tenant_schema}'
                )
            )
