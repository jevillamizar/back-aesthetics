"""
Comando para copiar usuarios de public schema a sus tenant schemas.

Uso:
  python manage.py migrate_users_to_tenants \
    --mapping admin@demo.com:demo_clinic doctor@nathaly.com:nathaly_pino

  python manage.py migrate_users_to_tenants \
    --mapping admin@demo.com:demo_clinic --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Copia usuarios de public.users_user a su tenant correspondiente'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mapping',
            nargs='+',
            help='Pares email:schema. Ej: admin@demo.com:demo_clinic',
            required=True,
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la migración sin crear usuarios',
        )

    def handle(self, *args, **options):
        mapping = {}
        for pair in options['mapping']:
            if ':' not in pair:
                self.stderr.write(self.style.ERROR(
                    f'Formato inválido: {pair}. Usar email:schema'
                ))
                continue
            email, schema = pair.split(':', 1)
            mapping[email.strip()] = schema.strip()

        for email, tenant_schema in mapping.items():
            self._migrate_user(email, tenant_schema, dry_run=options['dry_run'])

    def _migrate_user(self, email: str, tenant_schema: str, dry_run: bool) -> None:
        """Lee usuario de public y lo copia al tenant schema."""
        # Leer datos del usuario desde public.users_user con raw SQL
        # (la tabla puede no estar en el ORM si users ya fue movido a TENANT_APPS)
        user_data = self._read_public_user(email)
        if user_data is None:
            self.stderr.write(self.style.ERROR(
                f'Usuario {email} no encontrado en public.users_user'
            ))
            return

        if dry_run:
            self.stdout.write(f'[dry-run] {email} → {tenant_schema}')
            return

        with schema_context(tenant_schema):
            from users.models import User
            if User.objects.filter(email=email).exists():
                self.stdout.write(self.style.WARNING(
                    f'⚠️  {email} ya existe en {tenant_schema}, saltando'
                ))
                return

            user = User(
                email=user_data['email'],
                role=user_data['role'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                is_active=user_data['is_active'],
                is_staff=user_data['is_staff'],
                is_superuser=user_data['is_superuser'],
            )
            # Asignar el hash directamente sin re-hashear
            user.password = user_data['password']
            user.save()

            self.stdout.write(self.style.SUCCESS(
                f'✅ {email} → {tenant_schema}'
            ))

    def _read_public_user(self, email: str) -> dict | None:
        """Lee un usuario de public.users_user con raw SQL."""
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT email, password, role, first_name, last_name, '
                '       is_active, is_staff, is_superuser '
                'FROM public.users_user WHERE email = %s;',
                [email],
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                'email': row[0],
                'password': row[1],
                'role': row[2],
                'first_name': row[3],
                'last_name': row[4],
                'is_active': row[5],
                'is_staff': row[6],
                'is_superuser': row[7],
            }
