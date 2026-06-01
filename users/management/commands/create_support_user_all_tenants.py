"""
Comando para crear el usuario de soporte en todos los tenants existentes.

Uso:
  python manage.py create_support_user_all_tenants \
    --password=SoporteAesthetics2026!

Este comando es idempotente: si el usuario ya existe, lo omite.
"""
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context


SUPPORT_EMAIL = 'support@aesthetics.com'
DEFAULT_PASSWORD = 'SoporteAesthetics2026!'


class Command(BaseCommand):
    help = 'Crea el usuario de soporte en todos los tenants existentes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            default=DEFAULT_PASSWORD,
            help='Contraseña para el usuario de soporte (default: SoporteAesthetics2026!)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué se crearía sin crear nada',
        )

    def handle(self, *args, **options):
        from clinics.models import Clinic
        from users.models import User

        password = options['password']
        dry_run = options['dry_run']

        # Obtener todos los tenants (excluyendo public)
        clinics = Clinic.objects.exclude(schema_name='public')

        self.stdout.write(f'Tenants encontrados: {clinics.count()}')

        created_count = 0
        skipped_count = 0

        for clinic in clinics:
            result = self._create_support_in_tenant(
                clinic.schema_name, password, dry_run
            )
            if result == 'created':
                created_count += 1
            else:
                skipped_count += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY-RUN] Se crearían {created_count} usuarios, '
                    f'{skipped_count} ya existen'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Creados: {created_count}, Omitidos (ya existen): {skipped_count}'
                )
            )

    def _create_support_in_tenant(self, schema_name: str, password: str, dry_run: bool) -> str:
        """Crea el usuario de soporte en un tenant específico."""
        from users.models import User

        with schema_context(schema_name):
            if User.objects.filter(email=SUPPORT_EMAIL).exists():
                self.stdout.write(
                    f'  ⚠️  {schema_name}: {SUPPORT_EMAIL} ya existe'
                )
                return 'skipped'

            if dry_run:
                self.stdout.write(
                    f'  📝 {schema_name}: se crearía {SUPPORT_EMAIL}'
                )
                return 'created'

            User.objects.create_user(
                email=SUPPORT_EMAIL,
                password=password,
                role=User.Role.ADMIN,
                first_name='Soporte',
                last_name='Técnico',
                is_active=True,
                is_staff=True,
            )
            self.stdout.write(
                self.style.SUCCESS(f'  ✅ {schema_name}: {SUPPORT_EMAIL} creado')
            )
            return 'created'
