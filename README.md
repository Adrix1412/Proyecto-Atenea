# Atenea · base unificada de Alicia

Refactorización del ZIP entregado por Adrix. Conserva conversación con Ollama, Anthropic y Gemini, búsqueda opcional, voz con Whisper/Edge TTS, apertura confirmada de aplicaciones y avatar VTube Studio. El núcleo se reutiliza desde Django mediante una interfaz de memoria, sin importar Qt, micrófono ni hotkeys.

**Estado:** código implementado y probado con respuestas HTTP simuladas; no se han realizado llamadas a cuentas reales ni pruebas de audio/VTube Studio en tu PC. Los detalles y límites están en [VALIDATION.md](docs/VALIDATION.md). La configuración de ejemplo requiere elegir un modelo y completar tu endpoint o variable de entorno antes de arrancar. No contiene respuestas de demostración ni datos inventados.

## Inicio en Windows (PowerShell)

[Seguro] Esta entrega limita Python a **3.11–3.12**. La validación local se hizo en Python 3.12; CI incluye 3.11. Python 3.13 no está habilitado por la cadena de audio heredada de `pydub`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

Instala FFmpeg mediante un distribuidor confiable y comprueba `ffmpeg -version`. En Linux, necesitas además PortAudio del sistema; `pynput` requiere una sesión gráfica compatible. No ejecutes Alicia como administrador ni root.

Edita `config.yaml`:

- `llm.provider`: `ollama`, `anthropic` o `gemini`.
- `llm.model`: identificador real disponible en tu proveedor. No se adivina ni se fija un modelo posiblemente inexistente.
- Para Ollama: `llm.base_url` es el origen de tu servidor, sin `/api/chat`. HTTPS para servidores remotos; HTTP se admite solo en loopback explícito.
- Para Anthropic/Gemini: deja `base_url` vacío. Define `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` en el entorno del proceso. `api_key_env` permite cambiar **el nombre** de la variable, nunca contiene la clave.
- `search_enabled: true` habilita búsqueda; esta envía la consulta a servicios externos.
- `avatar.enabled: true` necesita una dirección IP loopback en `avatar.host` y la API activa en VTube Studio. El token se guarda fuera del repositorio, en datos del usuario.

Ejemplo de carga de la clave en la sesión PowerShell, sin escribirla en el comando ni en YAML:

```powershell
$secret = Read-Host "GEMINI_API_KEY" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
.\.venv\Scripts\python gui.py
```

El proceso hijo hereda esa variable. La GUI no guarda secretos. Cierra la sesión o elimina la variable al terminar si así lo requiere tu política de uso.

```powershell
.\.venv\Scripts\python main.py --text
.\.venv\Scripts\python main.py
.\.venv\Scripts\python gui.py
.\.venv\Scripts\python gui_ultimate.py
```

`--text` no carga micrófono, Whisper, Qt ni avatar. Para un entorno exclusivo de texto, instala `requirements-core.txt` y, si necesitas búsquedas, `pip install -e ".[search]"`.

## Uso y cambios de comportamiento

Mantén F9 para grabar, suéltala para enviar. La grabación se limita a 30 segundos por defecto. Esc o el botón Detener cierran la sesión. La inferencia se procesa en un trabajador separado; mientras está ocupado no empieza otra grabación. No existe cancelación remota de una solicitud LLM ya enviada: la GUI espera 5 segundos antes de cerrar forzosamente un proceso que no responde.

`gui.py` y `gui_ultimate.py` comparten controlador, configuración e historial. Ultimate conserva una presentación oscura, pero ya no tiene un segundo motor de configuración. El editor YAML permite modificar todos los campos y valida antes de guardar. Los cambios requieren reiniciar el asistente. Se eliminaron los controles ornamentales de pitch/estética y el escaneo de `.lnk`: no tenían una implementación fiable.

Usa “Añadir ejecutable al catálogo” para registrar aplicaciones. Los comandos son listas de argumentos fijos y su primer elemento es una ruta absoluta. No se aceptan comandos como cadenas, scripts, shells ni accesos directos. Cada petición del modelo para abrir una aplicación requiere una confirmación local que muestra el comando. En modo voz por terminal se imprime una línea JSON de aprobación que puedes copiar; en GUI aparece un diálogo. El modelo no puede añadir argumentos.

La respuesta se guarda antes de reproducirla. Si falla TTS, sigue disponible en memoria. Si falla el proveedor, no se guarda una respuesta ficticia ni un turno incompleto. La memoria persiste texto sin cifrar: usa una cuenta de sistema protegida y no guardes credenciales en conversaciones.

## Estructura

| Ubicación | Responsabilidad |
|---|---|
| `alicia_core/domain.py`, `service.py` | Contratos y caso de uso de conversación |
| `alicia_core/llm.py`, `adapters/providers.py` | Ciclo acotado de herramientas y formatos de los tres proveedores |
| `alicia_core/tools.py` | Registro cerrado, validación y autorización de herramientas |
| `alicia_core/adapters/sqlite_memory.py` | Memoria local transitoria, turnos atómicos |
| `alicia_core/django_app/` | Modelos, migración inicial, repositorio, endpoints e importador |
| `alicia_desktop/` | GUI, audio, hotkeys, lanzador, avatar y composición |
| Archivos `.py` en la raíz | Entradas públicas y fachadas de importación |
| `tests/` | Regresiones del núcleo, seguridad e integración Django |

Este repositorio contiene **una sola copia** de `alicia_core` y los adaptadores `alicia_desktop`. Para trabajar únicamente con el Core, instala `requirements-core.txt`: no instala audio, Qt ni hotkeys. `requirements.txt` agrega las dependencias de escritorio. La integración Django es opcional mediante `requirements-django.txt`. Importar `alicia_core` no inicializa componentes del escritorio. El avance y las limitaciones de Atenea están en `docs/atenea/`.

## Memoria e integración Django

Consulta [MIGRATION.md](docs/MIGRATION.md) antes de reutilizar una base vieja o importar rutas de aplicaciones desde tu ZIP privado. No se incluyen bases ni conversaciones personales. Para integrar con tu backend sigue [DJANGO.md](docs/DJANGO.md). Hay modelos y endpoints de integración; esta entrega no incluye una web React, una pantalla de login ni un despliegue.

## Desarrollo y GitHub

```bash
python -m pip install -r requirements-dev.txt
pytest -q
ruff check .
ruff format --check .
mypy alicia_core
python -m django check --settings=tests.settings
python -m django makemigrations --check --dry-run --settings=tests.settings
```

Con las dependencias de escritorio instaladas: `mypy alicia_core alicia_desktop`. `pyproject.toml` es la única definición de dependencias; los `requirements*.txt` seleccionan los extras. `constraints-tested-py312.txt` registra las versiones observadas en la validación local: úsalo con `pip install -c constraints-tested-py312.txt -r requirements.txt` para repetir esa resolución en Python 3.12. No sustituye la revisión periódica de dependencias ni es un lock multiplataforma con hashes.

Esta carpeta ya es la raíz del proyecto; `.github/workflows/ci.yml` comprueba SQLite y prepara otra ejecución sobre PostgreSQL 16. El workflow está incluido, **no ejecutado en GitHub**. El inventario inicial y el registro de la consolidación están en `docs/atenea/`.

Revisa `git status --short` antes de hacer commit. `.gitignore` excluye configuraciones privadas, bases, logs, tokens, entornos y cachés. No se incluye una licencia nueva: conserva la titularidad original y decide la licencia antes de autorizar redistribución pública.

## Explicación clave

- El núcleo recibe interfaces: cambiar SQLite por Django no modifica el caso de uso.
- El modelo propone herramientas; la aplicación valida y autoriza cada ejecución.
- Se guarda el turno completo con una revisión esperada: una respuesta concurrente no sobrescribe otra silenciosamente.
- El escritorio y la web ensamblan capacidades distintas; Django nunca registra el lanzador ni el avatar.

Avance de tareas persistentes: [diario SQLite y límites operativos](docs/atenea/04-tareas-persistentes.md).
