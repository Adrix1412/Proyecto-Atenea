# Cambios · 0.2.0

- Separación entre dominio, servicio, adaptadores, Django y escritorio.
- Tres proveedores REST mediante HTTPX, con validación de respuestas y errores seguros. Se eliminan el import obligatorio del SDK de Google y la dependencia de `requests`.
- Sustitución de las dependencias inconsistentes: se elimina Kokoro porque el motor real es Edge TTS; se declaran Edge TTS, pydub, websockets y platformdirs en el extra de escritorio.
- Tool calling acotado, sin ejecución automática de aplicaciones sin aprobación.
- Modelos Django, migración inicial, repositorio por propietario e importador SQLite original.
- Grabación limitada, trabajador separado, temporales compatibles con Windows, dispositivo de salida y sample rate aplicados al audio.
- VTS con acceso serializado, validación de APIError, token fuera del proyecto y cierre explícito.
- GUI compartida y dos temas; configuración validada, historial por repositorio, cierre del proceso y confirmaciones locales.
- Pruebas, tipado estricto, Ruff, CI y documentación de migración.

Cambios deliberadamente incompatibles: configuración antigua, `Memory.add`, firmas de fábrica LLM, comandos string y `.lnk`. Detalles en `docs/MIGRATION.md`.
