# Atenea — Fase 1: consolidación del Core

Fecha: 25 de septiembre de 2026. Esta entrega sustituye la estructura doble `Alicia-desktop-refactor/` + `alicia-core/` por **una sola raíz de proyecto** con un único paquete `alicia_core/` y los adaptadores `alicia_desktop/`. El informe `00-baseline.md` describe el ZIP recibido antes de la consolidación; por eso conserva el inventario histórico de dos variantes.

## Qué cambia

- `alicia_core/` permanece como fuente única para conversación, proveedores, herramientas, memoria y la integración Django opcional.
- `alicia_desktop/` contiene audio, GUI, lanzador, avatar y el importador seguro de rutas de aplicaciones creado al inicio de Fase 1.
- `requirements-core.txt` instala el proyecto con dependencias mínimas; `requirements.txt` añade escritorio; `requirements-django.txt` añade Django/búsqueda. Ya no hay que elegir entre dos distribuciones con el mismo paquete Python.
- El workflow de esta raíz comprueba además que instalar solo el Core no importa escritorio ni requiere PySide6. Su ejecución remota sigue pendiente hasta publicar el repositorio.
- No se cambió el comportamiento del caso de uso ni los modelos/migraciones Django. Los nombres Python `alicia_core` y `alicia_desktop` se mantienen para no romper imports existentes durante la migración a la marca Atenea.

## Evidencia en este entorno

| Verificación | Resultado |
|---|---|
| Instalación mínima, Python 3.12 | 13 paquetes; `import alicia_core` sin `alicia_desktop` ni PySide6; `uv pip check` correcto. |
| Instalación dev/Django, Python 3.12 | 50 pruebas aprobadas; mypy Core + migrador: 25 archivos sin errores. |
| Extras de escritorio, Python 3.12 en Linux | Instalados con `CC=gcc` por una dependencia nativa de `pynput`; mypy completo: 38 archivos sin errores; 74 paquetes compatibles. No se encendió micrófono ni GUI interactiva. |
| Ruff | Lint correcto; 73 archivos formateados. |
| Django | System check correcto; no hay migraciones pendientes. |
| Wheel | Se construyó e inspeccionó; incluye los módulos Core y escritorio exactamente desde la raíz única. |
| Hardware e integraciones externas | No ejecutados: Windows, F9, audio, VTube Studio, proveedores reales y PostgreSQL real quedan pendientes. |

**Para reproducir:** desde la raíz `Atenea/`, crear un venv Python 3.11–3.12, instalar `requirements-dev.txt`, ejecutar `pytest -q`, `ruff check .`, `ruff format --check .`, `mypy alicia_core`, `python -m django check --settings=tests.settings` y `python -m django makemigrations --check --dry-run --settings=tests.settings`. Para comprobar instalación mínima, usar otro venv con `requirements-core.txt` y `python -c "import alicia_core"`.

## Compatibilidad y reversión

El ZIP anterior se conserva como copia de reversión. Para quien instalaba la variante `alicia-core/`, ahora `cd Atenea` e instala `requirements-core.txt` en un venv nuevo. Los imports `alicia_core.*` permanecen iguales. No mezclar el venv antiguo de una variante con el nuevo proyecto: reinstalar dependencias en un venv limpio. No se modifica ningún `config.yaml`, base de datos ni token del usuario.

La memoria del esquema SQLite original se importa con el procedimiento de `docs/MIGRATION.md`. El importador de rutas lee el ZIP privado localmente y nunca incluye rutas ni claves en la entrega. Restaurar el proyecto anterior no revierte conversaciones creadas en una base nueva; conservar una copia consistente de la base antes de cambiar de versión.

## Estado de Fase 1

**Completado:** fuente Core única, instalación mínima comprobada, configuración antigua importable sin secretos, suite regresiva y documentación de reversión.

**Pendiente:** probar Windows/voz/avatar; medir latencias; evaluar la cancelación de operaciones bloqueantes y el ciclo de vida del proceso. Estas verificaciones no impiden avanzar en contratos y pruebas del Core, pero impiden afirmar compatibilidad total del escritorio en el PC real.

## Explicación clave

- [Seguro] Una fuente única impide que dos copias del Core diverjan silenciosamente.
- [Seguro] Instalar el proyecto sin el extra `desktop` mantiene el entorno mínimo aun cuando el repositorio incluya los archivos de escritorio.
- [Seguro] Las pruebas de empaquetado y regresión no sustituyen la comprobación física de voz, avatar y hotkeys.
