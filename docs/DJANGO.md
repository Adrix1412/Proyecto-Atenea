# Integración Django y PostgreSQL

## Instalación del paquete

[Seguro] Se utiliza Django 5.2 y Psycopg 3. La documentación oficial de Django 5.2 incluye PostgreSQL entre sus bases compatibles. La ejecución real contra PostgreSQL debe confirmarse en tu entorno o CI; esta sesión no tenía un servidor PostgreSQL.

Instala **una** variante:

```bash
python -m pip install -r requirements-django.txt
```

En el backend que ya tenga autenticación añade `alicia_core.django_app` a `INSTALLED_APPS`, conserva `SessionMiddleware`, `CsrfViewMiddleware` y `AuthenticationMiddleware`, e incluye las rutas:

```python
from django.urls import include, path

urlpatterns = [
    path("api/alicia/", include("alicia_core.django_app.urls")),
]
```

Copia `config.core.example.yaml` a un archivo privado `config.core.yaml`; completa proveedor, modelo y endpoint o variable de clave. Define `ALICIA_CONFIG_PATH` en los settings del proyecto con la ruta absoluta al archivo. No uses la configuración de escritorio en web.

`python manage.py migrate` crea las tablas. El esquema utiliza `AUTH_USER_MODEL`, con ID entero en el repositorio de este ejemplo. Se asume una única base Django por instancia; el ejemplo no implementa routers multibase.

## Proyecto ejecutable de referencia

Se incluye `examples/django_project/` y un `manage.py`. No tiene login: se integra con la autenticación de tu plataforma. Los endpoints sin sesión devuelven 401, y las solicitudes sin CSRF válido devuelven 403.

Variables requeridas para usar este proyecto:

| Variable | Uso |
|---|---|
| `DJANGO_SECRET_KEY` | Secreto aleatorio suministrado por tu entorno o plataforma |
| `DJANGO_ALLOWED_HOSTS` | Hosts reales separados por coma, sin esquema |
| `ALICIA_CONFIG` | Ruta absoluta a `config.core.yaml` |
| `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST` | Conexión al PostgreSQL de tu plataforma |
| `PGPORT` | Puerto; por defecto 5432 |
| `PGSSLMODE` | Por defecto `verify-full`; configura certificados del servidor |
| `GEMINI_API_KEY` o `ANTHROPIC_API_KEY` | Solo para el proveedor elegido |

`DJANGO_DEBUG` es falso por defecto; cookies seguras y redirección HTTPS están activadas. `ALICIA_DB_BACKEND=sqlite` selecciona explícitamente una base de desarrollo para probar sin PostgreSQL. Un error de PostgreSQL no provoca fallback silencioso a SQLite. Para desarrollo HTTP local debes seleccionar conscientemente `DJANGO_DEBUG=true` y configurar los hosts; no uses esa opción en producción. No se confía automáticamente en encabezados de proxy; configura tu proxy y `SECURE_PROXY_SSL_HEADER` según tu despliegue para evitar redirecciones HTTPS incorrectas.

Comandos tras establecer las variables:

```bash
python manage.py migrate
python manage.py check
python manage.py shell
```

Dentro de la shell, usa un usuario existente para crear la conversación:

```python
from django.contrib.auth import get_user_model
from alicia_core.django_app.models import Conversation

user = get_user_model().objects.get(username="tu_usuario_existente")
conversation = Conversation.objects.create(owner=user)
print(conversation.pk)
```

No se incluyen usuarios, contraseñas ni API keys de prueba reutilizables. El módulo `tests.settings` genera una clave efímera y solo sirve para pruebas.

## Contrato HTTP para React u otra interfaz

| Método/ruta | Entrada | Resultado |
|---|---|---|
| `POST /api/alicia/conversations/` | Sesión + CSRF | 201, `{"id":"uuid"}` |
| `POST /api/alicia/conversations/{uuid}/messages/` | JSON `{"message":"texto"}`, sesión + CSRF | 200, `{"reply":"texto"}` |

La interfaz debe enviar `Content-Type: application/json`, cookies de sesión y `X-CSRFToken` emitido por tu proyecto. Renderiza la respuesta como texto; no la insertes como HTML. No añadas `csrf_exempt` para resolver errores de integración.

Errores: 400 entrada inválida; 401 sin sesión; 403 CSRF; 404 conversación ajena/inexistente; 405 método incorrecto; 409 conflicto de revisión; 413 cuerpo demasiado grande; 415 tipo de contenido; 429 límite de frecuencia; 503 fallo de proveedor o persistencia. Los mensajes de error no incluyen detalles del proveedor. El control de frecuencia usa `cache.add`: **el caché local por defecto solo protege un proceso**. Configura un caché compartido con `add` atómico y un límite en el proxy/plataforma antes de exponer múltiples workers o un servicio público.

No hay streaming, WebSocket web, subida de audio, endpoints públicos de borrado de memoria ni cola de tareas en esta entrega. `ConversationService.reply` es síncrono: usa vistas síncronas o ejecútalo fuera del bucle de eventos si tu backend es asíncrono. Define cuotas, retención, autenticación real y límites de concurrencia en el proyecto anfitrión antes de producción.

## Verificación PostgreSQL

CI declara un servicio PostgreSQL 16 y ejecuta `tests/test_django.py`. Para hacerlo en tu entorno, usa una base exclusiva de pruebas y las variables `PG*`; el usuario de prueba necesita permiso para crear la base temporal de Django:

```bash
ALICIA_TEST_POSTGRES=1 pytest -q tests/test_django.py
```

Nunca dirijas estas pruebas a una base de producción. Con Psycopg instalado, la aplicación usa el ORM; no hay SQL SQLite embebido en el repositorio Django.
