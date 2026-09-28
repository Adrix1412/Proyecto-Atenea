# Proyecto Atenea — Fase 0: inventario y línea base

Fecha: 25 de septiembre de 2026. Fuente: `Alicia-refactor-completo(1).zip` y el plan maestro adjunto. La copia inspeccionada **no contiene historial Git ni configuración privada**, y las integraciones de hardware no están disponibles en este entorno Linux. Este informe no certifica comportamiento en la PC del propietario.

## 1. Veredicto y punto de partida

La fase de inventario y las pruebas automatizadas disponibles están terminadas. La puerta de salida completa de Fase 0 queda **pendiente**: no fue posible arrancar el flujo F9, probar audio/VTube Studio/Windows, conectar proveedores reales ni obtener métricas comparables de latencia o reposo. No avanzar a una reescritura del Core hasta completar estas verificaciones en el entorno de uso.

La entrega contiene **dos proyectos independientes que incluyen la misma copia de `alicia_core`**: `Alicia-desktop-refactor/` y `alicia-core/`. `diff -qr` no encontró diferencias entre sus paquetes Core. No instalarlos en un mismo entorno. El proyecto no es la Alicia monolítica descrita en `ALICIA_DOCS.md`: parte de la extracción prevista para Fase 1 ya existe. El siguiente incremento debe validar y completar esa extracción, no volver a empezar.

## 2. Mapa de componentes verificado

| Componente | Ubicación | Estado observado |
|---|---|---|
| Composición y conversación | `alicia_core/service.py`, `domain.py` | Servicio síncrono con protocolos de chat y memoria; validación de texto y control de revisiones. |
| LLM y herramientas | `alicia_core/llm.py`, `tools.py`, `adapters/providers.py` | Ollama/Anthropic/Gemini por HTTP; registro cerrado de tres posibles tools, según composición; presupuestos por turno y confirmación local de apertura. Las llamadas usan un argumento string por tool. |
| Memoria local | `alicia_core/adapters/sqlite_memory.py`, `legacy.py` | Turnos atómicos y lectura/importación del esquema SQLite anterior; no hay conversaciones reales en el ZIP. |
| Django | `alicia_core/django_app/` | Modelos, migración inicial, repositorio por propietario, endpoints POST para crear conversación y conversar, importador SQLite antiguo. Es una integración de ejemplo, no el backend productivo del usuario. |
| Escritorio | `alicia_desktop/main.py`, `voice.py`, `stt.py`, `tts.py`, `gui.py`, `avatar.py` | CLI texto/voz, GUI Qt, hotkey F9, Whisper, Edge TTS y cliente VTube Studio; código presente, hardware sin verificar aquí. |
| Aplicaciones | `alicia_desktop/launcher.py`, `factory.py` | Catálogo de ejecutables absolutos con argumentos fijos; validación y confirmación; `Popen(shell=False)` al ejecutar. |
| Búsqueda | `alicia_core/adapters/search.py` | Tool opcional de consulta externa; no se probó servicio público real. |
| Tests/CI | `tests/`, `.github/workflows/ci.yml` | Tests simulados y flujo de CI definido; no hay ejecución remota comprobable de este ZIP. |

Flujo actual: entrada CLI/GUI/voz → composición escritorio o Django → `ConversationService` → `LLMClient`/`ToolRegistry` y `MemoryRepository` → adaptadores externos. No existe en esta entrega `TaskExecutor` persistente, `DeviceRegistry`, agentes remotos, cliente Android, scheduler ni canal WebSocket Core↔agente. El WebSocket existente pertenece solo al cliente local de VTube Studio.

## 3. Diferencias relevantes frente a la documentación inicial

| Descripción anterior | Código recibido | Implicación |
|---|---|---|
| `main.py` orquesta todo en un proceso monolítico | `main.py` raíz es fachada; `alicia_core` está separado de `alicia_desktop` y se compone desde CLI o Django | Fase 1 parcialmente implementada; evaluar brechas reales. |
| `llm.py` define y ejecuta tools del escritorio | Core ejecuta un `ToolRegistry` inyectado; composición de escritorio añade apertura y expresiones; web añade búsqueda opcional | No acoplar Core de nuevo al SO. |
| `hands.py` / `usar_computadora` controla pantalla en hasta 15 pasos | No están presentes en el ZIP inspeccionado | Funcionalidad retirada; restaurarla requiere diseño nuevo, permisos R2 y pruebas. No declarar preservación de esa función. |
| `launcher.py` acepta catálogo flexible | Exige ruta absoluta, lista fija, ejecutable existente y aprobación local | Cambio de compatibilidad deliberado; migrar configuración antigua antes de ejecutar. |
| SQLite guarda mensajes; PostgreSQL planificado | SQLite nuevo y adaptador Django ORM ya existen | Solo hay pruebas SQLite; PostgreSQL real pendiente. No hay exportador del esquema SQLite nuevo hacia Django. |
| `config.yaml` contiene API key | Modelo de configuración la obtiene del entorno; ejemplos no contienen credenciales reales detectables | Revisar historial Git y entorno real, ausentes del ZIP. |
| VTS token junto al proyecto | Se guarda en datos privados del usuario mediante `platformdirs` | Token antiguo no se reutiliza automáticamente. |

## 4. Verificación reproducible realizada

Entorno: Linux, CPython 3.12.14; entornos `.venv` separados con `uv pip install -r requirements-dev.txt`. No se ejecutaron herramientas de SO ni proveedores externos. La prueba de dependencias de escritorio **no** se instaló.

| Comando / prueba | Resultado de esta sesión |
|---|---|
| `unzip -Z -t` | 147 entradas, 276 953 bytes descomprimidos; ZIP legible. |
| `diff -qr` de ambos `alicia_core/` | Sin diferencias. |
| Escritorio: `.venv/bin/python -m pytest -q` | 46 passed. |
| Core independiente: `.venv/bin/python -m pytest -q` | 37 passed; son un subconjunto de los 46, no 37 pruebas adicionales. |
| Escritorio: `ruff check .` y `ruff format --check .` | Aprobados; 70 archivos formateados. |
| Escritorio: `mypy alicia_core` | Aprobado; 24 archivos fuente. |
| Escritorio: `django check` y `makemigrations --check --dry-run` con `tests.settings` | Sin incidencias y sin migraciones pendientes. |
| Ambas variantes: `uv pip check --python .venv/bin/python` | Dependencias instaladas compatibles. |
| Escritorio: `compileall -q alicia_core alicia_desktop tests` | Aprobado. |
| Escritorio: `mypy alicia_core alicia_desktop` | No concluyente: 12 errores por bibliotecas de escritorio **no instaladas** en este venv (`PySide6`, `numpy`, `websockets`, `platformdirs`, `edge_tts`); reintentar tras instalar extras `desktop`. |
| Búsqueda orientativa de credenciales en archivos del ZIP | Sin coincidencias con el patrón de asignaciones de tokens largos. No sustituye revisión de secretos ni historial Git. |

Para repetir en Linux/macOS, desde cada variante y con un entorno Python 3.11–3.12:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy alicia_core
uv pip check --python .venv/bin/python
```

En Windows sustituir `.venv/bin/python` por `.venv\Scripts\python.exe`. Para validar tipado de escritorio, instalar también `requirements.txt` en el entorno **de esa variante**, ejecutar `mypy alicia_core alicia_desktop` y las pruebas manuales del README. Una instalación de dependencias no prueba dispositivos físicos ni proveedores remotos.

## 5. Riesgos y decisiones antes de Fase 1

1. **Alta — producto distinto al documento de origen.** El ZIP refactorizado omite control de pantalla y cambia formato de configuración y APIs de memoria. Confirmar si `usar_computadora` debe recuperarse y proporcionar el repositorio original si esa función se considera indispensable. Mantenerla deshabilitada mientras no tenga permisos R2 y pruebas.
2. **Alta — integración web no equivale a backend existente.** La carpeta Django es una app de ejemplo. Antes de incorporar a Atenea o a otro Django, obtener el backend real y resolver identidad, modelos, PK del usuario, migraciones y propiedad de datos. No ejecutar una segunda app Django paralela sin esa decisión.
3. **Alta — pruebas físicas faltantes.** F9, audio, VTS, apertura en Windows y comportamiento de GUI no están verificados en el equipo real; la documentación anterior reporta pruebas offscreen de otra sesión, no equivalentes a las actuales.
4. **Media — fuente compartida duplicada.** Dos copias iguales de `alicia_core` pueden divergir al evolucionar Atenea. Elegir un paquete canónico/monorepo y adaptar instalación/CI antes de modificar el núcleo en dos lugares.
5. **Media — migración de memoria incompleta.** El importador acepta SQLite original; no exporta la memoria generada por la nueva versión al Django posterior. Preparar exportación y restauración ensayadas antes de cambiar de repositorio.
6. **Media — política de permisos aún local.** La confirmación actual es callback de sesión; no es aprobación duradera con identidad, caducidad y hash de argumentos. Nunca extrapolarla a agentes remotos.
7. **Media — presupuesto de proveedores.** Los tests HTTP están simulados; cuotas, modelos y latencias son desconocidos. No fijar métricas ni afirmar disponibilidad de free tiers.
8. **Media — historial Git ausente.** No se puede verificar si hubo secretos en commits, licencias, releases o estado de CI remoto. Revisar el repositorio canónico antes de publicar o conectar claves.

## 6. Métricas aún no medidas y procedimiento

No hay p50/p95 honesto para STT, LLM, TTS, avatar, CPU/RAM en reposo o consumo Android: faltan hardware, modelos descargados, cuentas/credenciales y condiciones controladas. En una PC Windows de prueba: ejecutar al menos 20 solicitudes comparables por ruta después de calentamiento, registrar tiempos monotónicos por etapa y calcular percentiles a partir de muestras; anotar CPU/RAM en reposo tras 10 minutos y versión/configuración sin secretos. Separar resultados locales y nube, y registrar fallos/timeout. No enviar transcripciones ni capturas personales a la telemetría.

## 7. Puerta de salida y rollback

| Criterio | Estado | Evidencia / acción faltante |
|---|---|---|
| Código y diferencias documentadas | **Verificado** | Inventario, mapa y tabla anteriores. |
| Tests y checks disponibles | **Verificado** | 46 + 37 tests, Ruff, mypy Core, Django, compileall. |
| Función previa preservada en PC real | **Pendiente** | Arranque texto, voz F9, GUI, VTS y apertura confirmada con configuración del propietario. Control de pantalla no existe en esta entrega. |
| Seguridad de la fase | **Parcial** | Tests de rechazo y escaneo orientativo; faltan Git, credenciales reales y pruebas sobre SO. |
| Recuperación de datos | **Pendiente** | Probar backup/restore de base SQLite propia y migración del esquema nuevo si se moverá a Django. |
| Métricas de rendimiento | **Pendiente** | Medir en hardware y proveedores elegidos con metodología anterior. |
| Integración PostgreSQL | **Pendiente** | Prueba real de DB; no inferirla de SQLite ni del workflow. |

**Rollback de esta fase:** no se cambió código de ejecución. El ZIP adjunto original sigue intacto. Conservar respaldos consistentes de cualquier DB real antes de adoptar este refactor; restaurar el entorno/configuración anterior si las pruebas de Windows fallan. Este informe no ejecuta migraciones ni despliegues.

**Próximo trabajo propuesto:** completar las pruebas Windows y elegir fuente canónica del Core. Después, reinterpretar Fase 1 como auditoría de brechas: imports Core sin GUI, cancelación limpia, interfaz de memoria, adaptadores y regresión del flujo F9. No crear un segundo `ConversationService` ni repetir una extracción ya hecha.

## Explicación clave

- [Seguro] Un test simulado aprueba lógica aislada, no demuestra compatibilidad con Windows, audio, VTS ni proveedores reales.
- [Seguro] La duplicación del Core crea riesgo de divergencia al modificar dos variantes.
- [Probable] La Fase 1 será más corta si se trabaja sobre este refactor; requiere confirmar qué funciones retiradas son obligatorias.
