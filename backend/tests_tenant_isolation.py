"""
Tests de aislamiento físico por tenant (Option A).

Tarea 1 — users en TENANT_APPS:
  - users_user existe en el schema del tenant.
  - Usuarios creados en un tenant NO son visibles en otro.
  - El comando migrate_users_to_tenants copia usuarios correctamente.

Tarea 2 — TenantAuthBackend simplificado:
  - El backend autentica sin necesidad de FK a Clinic.
  - Intentar autenticar en public schema retorna None de forma segura.
  - El aislamiento entre tenants es automático (no por is_superuser check).
"""
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import schema_context

from clinics.models import Clinic, Domain
from users.models import User


class UsersTableInTenantSchemaTests(TenantTestCase):
    """Verifica que users_user existe en el schema del tenant tras mover a TENANT_APPS."""

    def test_users_table_exists_in_tenant_schema(self) -> None:
        """La tabla users_user debe existir en el schema del tenant."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS ("
                "  SELECT FROM information_schema.tables "
                "  WHERE table_schema = %s AND table_name = 'users_user'"
                ");",
                [self.tenant.schema_name],
            )
            exists = cursor.fetchone()[0]
        self.assertTrue(exists, f'users_user no existe en schema {self.tenant.schema_name}')

    def test_user_created_in_tenant_schema(self) -> None:
        """Un usuario creado dentro del tenant debe vivir en su schema."""
        user = User.objects.create_user(
            email='doctor@tenant-test.com',
            password='Test1234!',
            role=User.Role.DOCTOR,
            is_active=True,
        )
        self.assertIsNotNone(user.pk)

        # Verificar con raw SQL que el registro está en el schema del tenant
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT COUNT(*) FROM "{self.tenant.schema_name}".users_user '
                f"WHERE email = %s;",
                ['doctor@tenant-test.com'],
            )
            count = cursor.fetchone()[0]
        self.assertEqual(count, 1)


class TenantUserIsolationTests(TenantTestCase):
    """Verifica que usuarios de un tenant no son visibles en otro."""

    @classmethod
    def setup_tenant(cls, tenant):
        """Configuración del tenant creado por TenantTestCase."""
        tenant.name = 'Test Clinic'
        tenant.slug = 'test-clinic'

    def test_user_created_in_tenant_stays_isolated(self) -> None:
        """
        Un usuario creado en tenant A no debe ser visible desde tenant B.
        """
        # Crear usuario en el tenant principal (self.tenant)
        User.objects.create_user(
            email='isolated@clinica-a.com',
            password='Test1234!',
            role=User.Role.ADMIN,
            is_active=True,
        )

        # Crear un segundo tenant desde el schema public (requerido por django-tenants)
        with schema_context('public'):
            tenant_b = Clinic.objects.create(
                name='Clinic B',
                slug='clinic-b',
                schema_name='clinic_b_test',
            )
            Domain.objects.create(
                domain='clinic-b.test.com',
                tenant=tenant_b,
                is_primary=True,
            )

        # Verificar que el usuario NO es visible en tenant B
        with schema_context(tenant_b.schema_name):
            count = User.objects.filter(email='isolated@clinica-a.com').count()
            self.assertEqual(
                count,
                0,
                'El usuario de tenant A es visible en tenant B — falla el aislamiento',
            )

        # Verificar que el usuario SÍ es visible en su propio tenant
        user_count = User.objects.filter(email='isolated@clinica-a.com').count()
        self.assertEqual(user_count, 1)

    def test_same_email_different_tenants(self) -> None:
        """
        Con Option A, el mismo email puede existir en dos tenants.
        El constraint unique=True en email es per-schema.
        """
        # Crear usuario en tenant principal
        User.objects.create_user(
            email='shared@email.com',
            password='Test1234!',
            role=User.Role.ADMIN,
            is_active=True,
        )

        # Crear segundo tenant desde schema public
        with schema_context('public'):
            tenant_b = Clinic.objects.create(
                name='Clinic C',
                slug='clinic-c',
                schema_name='clinic_c_test',
            )
            Domain.objects.create(
                domain='clinic-c.test.com',
                tenant=tenant_b,
                is_primary=True,
            )

        # Crear usuario con el MISMO email en tenant B — no debe fallar
        with schema_context(tenant_b.schema_name):
            user_b = User.objects.create_user(
                email='shared@email.com',
                password='OtherPass1234!',
                role=User.Role.ADMIN,
                is_active=True,
            )
            self.assertIsNotNone(user_b.pk)

        # Verificar que cada tenant tiene exactamente 1
        self.assertEqual(User.objects.filter(email='shared@email.com').count(), 1)
        with schema_context(tenant_b.schema_name):
            self.assertEqual(User.objects.filter(email='shared@email.com').count(), 1)


class MigrateUsersToTenantsCommandTests(TenantTestCase):
    """Tests para el comando migrate_users_to_tenants.

    En el entorno de test, public.users_user no existe (users está en TENANT_APPS).
    Creamos la tabla de respaldo en setUp para simular el escenario de producción.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Migrate Test Clinic'
        tenant.slug = 'migrate-test'

    def setUp(self) -> None:
        """Crea public.users_user de respaldo (simula tabla pre-migración).

        En producción, esta tabla ya existe. En el entorno de test,
        la recreamos manualmente porque users fue movido a TENANT_APPS.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                'CREATE TABLE IF NOT EXISTS public.users_user ('
                '  id SERIAL PRIMARY KEY,'
                '  password VARCHAR(128) NOT NULL,'
                '  is_superuser BOOLEAN NOT NULL DEFAULT FALSE,'
                '  email VARCHAR(254) NOT NULL UNIQUE,'
                '  role VARCHAR(20) NOT NULL DEFAULT \'ADMIN\','
                '  is_staff BOOLEAN NOT NULL DEFAULT FALSE,'
                '  is_active BOOLEAN NOT NULL DEFAULT TRUE,'
                '  first_name VARCHAR(150) NOT NULL DEFAULT \'\','
                '  last_name VARCHAR(150) NOT NULL DEFAULT \'\','
                '  date_joined TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),'
                '  document_type VARCHAR(5) NOT NULL DEFAULT \'CC\','
                '  document_number VARCHAR(30) NOT NULL DEFAULT \'\','
                '  phone VARCHAR(30) NOT NULL DEFAULT \'\','
                '  profession VARCHAR(100) NOT NULL DEFAULT \'\','
                '  specialty VARCHAR(100) NOT NULL DEFAULT \'\','
                '  university VARCHAR(150) NOT NULL DEFAULT \'\','
                '  rethus_number VARCHAR(50) NOT NULL DEFAULT \'\','
                '  rethus_status VARCHAR(15) NOT NULL DEFAULT \'ACTIVE\','
                '  certifying_entity VARCHAR(150) NOT NULL DEFAULT \'\','
                '  bio TEXT NOT NULL DEFAULT \'\','
                '  professional_seal VARCHAR(255) NOT NULL DEFAULT \'\','
                '  notes TEXT NOT NULL DEFAULT \'\','
                '  photo VARCHAR(100) NOT NULL DEFAULT \'\','
                '  last_login TIMESTAMP WITH TIME ZONE,'
                '  graduation_year SMALLINT'
                ');'
            )

    def tearDown(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS public.users_user;')
        super().tearDown()

    def _create_public_user(self, email: str, role: str = 'ADMIN') -> None:
        """Crea un usuario directamente en public.users_user (tabla de respaldo)."""
        from django.contrib.auth.hashers import make_password

        hashed = make_password('TestPass1234!')
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO public.users_user '
                '(password, is_superuser, email, role, is_staff, is_active, '
                ' first_name, last_name, date_joined) '
                'VALUES (%s, FALSE, %s, %s, FALSE, TRUE, '
                " '', '', NOW());",
                [hashed, email, role],
            )

    def test_migrate_command_copies_user_to_tenant(self) -> None:
        """El comando copia un usuario de public al tenant especificado."""
        self._create_public_user('migrate-me@test.com', 'ADMIN')

        out = StringIO()
        call_command(
            'migrate_users_to_tenants',
            mapping=[f'migrate-me@test.com:{self.tenant.schema_name}'],
            stdout=out,
        )

        # Verificar que el usuario existe en el schema del tenant
        user = User.objects.get(email='migrate-me@test.com')
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_active)
        self.assertIn('migrate-me@test.com', out.getvalue())

    def test_migrate_command_dry_run(self) -> None:
        """Con --dry-run no crea usuarios reales."""
        self._create_public_user('dryrun@test.com', 'DOCTOR')

        out = StringIO()
        call_command(
            'migrate_users_to_tenants',
            mapping=[f'dryrun@test.com:{self.tenant.schema_name}'],
            dry_run=True,
            stdout=out,
        )

        # Verificar que NO se creó en el tenant
        count = User.objects.filter(email='dryrun@test.com').count()
        self.assertEqual(count, 0)
        self.assertIn('dry-run', out.getvalue())

    def test_migrate_command_nonexistent_email(self) -> None:
        """Email que no existe en public → mensaje de error, no exception."""
        err = StringIO()
        call_command(
            'migrate_users_to_tenants',
            mapping=[f'ghost@test.com:{self.tenant.schema_name}'],
            stderr=err,
        )
        self.assertIn('ghost@test.com', err.getvalue())


# ─── Tarea 5: Comando create_tenant_admin ─────────────────────────────


class CreateTenantAdminCommandTests(TenantTestCase):
    """Tests para el comando create_tenant_admin."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Create Admin Test Clinic'
        tenant.slug = 'create-admin-test'

    def test_create_tenant_admin_creates_in_correct_schema(self) -> None:
        """Crea el usuario ADMIN en el schema del tenant especificado."""
        out = StringIO()
        call_command(
            'create_tenant_admin',
            tenant=self.tenant.schema_name,
            email='newadmin@test.com',
            password='AdminPass1234!',
            first_name='Nuevo',
            last_name='Admin',
            stdout=out,
        )

        # Verificar mensaje de éxito
        self.assertIn('newadmin@test.com', out.getvalue())
        self.assertIn('creado exitosamente', out.getvalue())

        # Verificar que existe en el tenant
        self.assertTrue(User.objects.filter(email='newadmin@test.com').exists())
        user = User.objects.get(email='newadmin@test.com')
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)

    def test_create_tenant_admin_fails_if_email_exists(self) -> None:
        """Email duplicado en el mismo tenant → CommandError."""
        # Crear usuario existente
        User.objects.create_user(
            email='existing@test.com',
            password='Existing1234!',
            role=User.Role.ADMIN,
            is_active=True,
        )

        err = StringIO()
        with self.assertRaises(Exception):
            call_command(
                'create_tenant_admin',
                tenant=self.tenant.schema_name,
                email='existing@test.com',
                password='NewPass1234!',
                stderr=err,
            )

    def test_create_tenant_admin_creates_admin_role(self) -> None:
        """Verifica que el usuario creado tiene role=ADMIN."""
        call_command(
            'create_tenant_admin',
            tenant=self.tenant.schema_name,
            email='rolecheck@test.com',
            password='RoleCheck1234!',
        )

        user = User.objects.get(email='rolecheck@test.com')
        self.assertEqual(user.role, User.Role.ADMIN)


# ─── Tarea 2: TenantAuthBackend simplificado post-Option A ───────────


class TenantAuthBackendOptionATests(TenantTestCase):
    """
    Tarea 2 — Verifica el backend simplificado con Option A.

    Con users en TENANT_APPS:
    - No se necesita check de clinic FK ni is_superuser.
    - El ORM aísla automáticamente por schema.
    - Intentar auth en public schema debe retornar None de forma segura.
    """

    def setUp(self) -> None:
        from django.test import RequestFactory

        from backend.tenant_permissions import TenantAuthBackend

        self.backend = TenantAuthBackend()
        self.request = RequestFactory().post('/api/auth/login/')

        self.admin = User.objects.create_user(
            email='admin@tarea2.com',
            password='Admin1234!',
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=True,
        )
        self.doctor = User.objects.create_user(
            email='doctor@tarea2.com',
            password='Doctor1234!',
            role=User.Role.DOCTOR,
            is_active=True,
        )

    def test_admin_autentica_sin_clinic_fk(self) -> None:
        """ADMIN se autentica correctamente — no se necesita FK a Clinic."""
        result = self.backend.authenticate(
            self.request,
            email='admin@tarea2.com',
            password='Admin1234!',
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.admin.pk)

    def test_doctor_autentica_sin_clinic_fk(self) -> None:
        """DOCTOR se autentica correctamente — no se necesita FK a Clinic."""
        result = self.backend.authenticate(
            self.request,
            email='doctor@tarea2.com',
            password='Doctor1234!',
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.doctor.pk)

    def test_autenticacion_en_public_schema_retorna_none(self) -> None:
        """
        En public schema, users_user no existe → authenticate devuelve None.
        No debe lanzar excepción (ProgrammingError manejado internamente).
        """
        with schema_context('public'):
            result = self.backend.authenticate(
                self.request,
                email='admin@tarea2.com',
                password='Admin1234!',
            )
        self.assertIsNone(result)

    def test_usuario_de_otro_tenant_no_visible(self) -> None:
        """
        Un usuario de tenant A no puede autenticarse en tenant B.
        La tabla users_user del tenant B no contiene al usuario A.
        """
        # Crear tenant B
        with schema_context('public'):
            tenant_b = Clinic.objects.create(
                name='Tenant B',
                slug='tenant-b',
                schema_name='tenant_b_auth_test',
            )
            Domain.objects.create(
                domain='tenant-b.test.com',
                tenant=tenant_b,
                is_primary=True,
            )

        # Intentar autenticar usuario de tenant A en schema de tenant B
        with schema_context(tenant_b.schema_name):
            result = self.backend.authenticate(
                self.request,
                email='admin@tarea2.com',
                password='Admin1234!',
            )
        self.assertIsNone(
            result,
            'Usuario de tenant A fue autenticado en tenant B — falla el aislamiento',
        )
