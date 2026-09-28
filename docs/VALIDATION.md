# Validación histórica del ZIP de origen

Este registro corresponde a la entrega con dos variantes del 23 de septiembre de 2026. Para las verificaciones de la base unificada consulta `docs/atenea/01-consolidacion.md`.

Fecha de entrega: 23 de septiembre de 2026. Entorno de ejecución: Linux, CPython 3.12.14. Las pruebas usan datos sintéticos y respuestas HTTP simuladas, nunca conversaciones ni claves reales.

| Comprobación | Resultado observado |
|---|---|
| Suite en Alicia-desktop-refactor | **46 pruebas aprobadas** |
| Suite en alicia-core, entorno virtual separado | **37 pruebas aprobadas**; corresponden al subconjunto compartido, no a 37 casos nuevos |
| Mypy estricto, núcleo + escritorio | Correcto, 37 archivos fuente |
| Mypy estricto, núcleo independiente | Correcto, 24 archivos fuente |
| Ruff y formato en ambas variantes | Correcto |
| Compilación Python | Correcta |
| Django system check | Sin incidencias |
| Comparación de modelos y migraciones | Sin cambios pendientes |
| pip check en ambos entornos | Sin requisitos incompatibles |
| Instalación independiente del núcleo | Correcta; PySide6, sounddevice, faster_whisper, pynput y alicia_desktop no instalados |
| GUI clásica y oscura (Qt offscreen) | Construcción, validación del YAML, lectura de salida de un subproceso y cierre correctos |
| Igualdad del paquete compartido | Los 27 archivos de alicia_core son idénticos en ambas variantes |
| Revisión del archivo final | Exclusión de secretos, bases, configuraciones privadas, cachés y entornos; integridad ZIP comprobada |

## Qué verifican las pruebas

- Rechazo de comandos string, shells, scripts, accesos directos y argumentos inválidos.
- Popen con lista fija y shell=False; ejecución real simulada, no se abrió ninguna aplicación del usuario.
- Confirmación obligatoria, herramientas desconocidas rechazadas y supresión de llamadas duplicadas en un turno.
- Presupuesto de rondas y rechazo de lotes de herramientas excesivos antes de ejecutarlos.
- Contratos REST de Ollama, Anthropic y Gemini; IDs/firmas conservados mediante fixtures.
- Timeouts, HTTP no exitoso, JSON inválido, respuesta demasiado grande y candidatos Gemini vacíos.
- Turnos atómicos, rollback ante fallo del segundo mensaje, conflicto de revisiones e invalidación tras borrar memoria.
- Importación SQLite original en escritorio y Django: dry-run, idempotencia, timestamps, solo lectura y rechazo sin inserciones parciales.
- Autenticación, CSRF, métodos HTTP, acceso de otro propietario, validación de JSON, tamaño máximo y límite básico de frecuencia.
- Ausencia de dependencias de escritorio en las importaciones del núcleo.

## No verificado en vivo

| Integración | Motivo / paso pendiente |
|---|---|
| Proveedores LLM y búsqueda pública | No se usaron cuentas, cuotas ni servicios externos reales; configurar y probar en tu entorno |
| Grabación/reproducción de audio | El entorno carece de PortAudio y de dispositivos de audio; importar la ruta de voz detectó esta dependencia del sistema |
| Whisper transcribiendo | Adaptador importado; no se descargó ni ejecutó un modelo |
| VTube Studio | Adaptador importado; no hay aplicación VTS ni modelo Live2D disponible |
| Hotkeys globales | No hay sesión gráfica interactiva del usuario; no se probaron las teclas físicas |
| PostgreSQL real | No había servidor PostgreSQL; CI incluye la ejecución para PostgreSQL 16 |
| Windows/macOS y Python 3.11 | No se ejecutaron en esta sesión; CI declara Python 3.11/3.12 en Linux |
| Workflow remoto | Archivo creado, pero el proyecto no se ha publicado ni ejecutado en GitHub |

[Seguro] Instalar un paquete Python no instala necesariamente bibliotecas nativas del sistema. Se instaló la cadena Python de escritorio, pero la ruta de audio sigue requiriendo PortAudio en Linux y FFmpeg para decodificar voz. La GUI y el modo texto permanecen separados de esa ruta.

Esto es una base refactorizada y verificable para integración. No certifica un despliegue productivo ni ausencia total de vulnerabilidades.
