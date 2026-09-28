# Migración desde el ZIP original

## Configuración

Crea una configuración nueva desde la plantilla. La validación rechaza campos desconocidos para que una configuración antigua no parezca funcionar ignorando valores.

| Antes | Ahora |
|---|---|
| `llm.api_key` | Variable de entorno; `api_key_env` contiene solo su nombre |
| `anthropic_model` / `gemini_model` | `llm.model` según el proveedor seleccionado |
| `hotkey.key`, `hotkey.mode` | `hotkey: f9`; modo hold implementado |
| `memory.db_path` | `memory_path` para escritorio; Django configura su propia base |
| `audio.silence_timeout_sec` | `audio.max_recording_sec`; ahora limita duración real, no detecta silencio |
| `apps.nombre: "comando"` | Lista con ruta absoluta al ejecutable y argumentos fijos |
| `tts.provider` | Eliminado: el adaptador implementado es Edge TTS |
| `vts_token.txt` junto al código | Datos privados del usuario mediante `platformdirs` |

No se reutiliza automáticamente un token VTS viejo; vuelve a autorizar el plugin. No se encontró un archivo privado de configuración o tokens en el ZIP revisado. La cadena `tu_key_aca` de la plantilla original era un marcador, no se trasladó como credencial.

## Importar rutas de aplicaciones desde el ZIP privado

Si conservas una copia del ZIP original con `alicia/config.yaml`, puedes crear una configuración nueva en tu PC Windows sin extraer ni copiar al repositorio sus claves, token, historial o logs. **No subas ese ZIP ni el `config.yaml` generado a GitHub.** En PowerShell, desde la carpeta `Atenea`:

```powershell
.\.venv\Scripts\python -m alicia_desktop.migrate_legacy_config "C:\ruta\privada\alicia.zip"
.\.venv\Scripts\python -m alicia_desktop.migrate_legacy_config "C:\ruta\privada\alicia.zip" --write
```

El primer comando es una simulación y solo indica cuántas aplicaciones se conservarán y cuáles requieren revisión. El segundo crea `config.yaml` únicamente si no existe. No imprime rutas ni secretos. Conserva las rutas absolutas de ejecutables y busca en el `PATH` las aplicaciones antiguas que solo tenían un nombre. Si una no se resuelve o se trata de un script, se omite para que la añadas desde la GUI con su ruta absoluta. La configuración resultante se valida de nuevo en Windows; la presencia del ejecutable se comprueba al abrirlo.

El importador no traslada `api_key`, `system_prompt`, token VTS ni la ruta de memoria antigua. Configura la API key mediante `GEMINI_API_KEY` o `ANTHROPIC_API_KEY` en el entorno. La memoria antigua requiere el procedimiento independiente de abajo. El valor antiguo `silence_timeout_sec` pasa a ser duración máxima de grabación; no reproduce detección de silencio.

## Memoria antigua hacia escritorio

1. Detén la aplicación original.
2. Conserva una copia de respaldo consistente de la base SQLite; si utiliza WAL, usa la API de backup de SQLite o ciérrala limpiamente antes de copiarla.
3. Configura `memory_path` a **otro archivo**, fuera de la ubicación del original.
4. Ejecuta con tus rutas reales:

```bash
python import_memory.py /ruta/absoluta/alicia_memory.db --config config.yaml --dry-run
python import_memory.py /ruta/absoluta/alicia_memory.db --config config.yaml
```

`--dry-run` valida el contenido y puede crear las tablas vacías del destino; no inserta mensajes. La importación preserva roles, orden y timestamps. El destino debe estar vacío. Repetir el mismo historial en la misma conversación devuelve cero importados. No se deduplican por texto: mensajes iguales pueden ser legítimos.

## Memoria antigua hacia PostgreSQL/Django

Configura Django como se indica en `DJANGO.md`, aplica migraciones y crea una conversación del propietario correcto. Usa su UUID e ID de usuario reales:

```bash
python manage.py import_alicia_sqlite /ruta/absoluta/alicia_memory.db --conversation UUID_REAL --owner ID_ENTERO --dry-run
python manage.py import_alicia_sqlite /ruta/absoluta/alicia_memory.db --conversation UUID_REAL --owner ID_ENTERO
```

Este comando lee únicamente el esquema original `exchanges(id,timestamp,role,content)` mediante conexión de solo lectura. Valida antes de insertar y escribe dentro de una única transacción. Registra un SHA-256 del contenido lógico para impedir repetir la misma importación. No modifica la fuente. Si la conversación ya tiene mensajes de otro origen, falla explícitamente en lugar de mezclarlos. Admite hasta 100 MB y 100 000 mensajes; rechaza un rol inválido, timestamp inválido o texto fuera de límites sin truncarlo silenciosamente.

No hay exportador del nuevo esquema de escritorio `messages` hacia Django en esta versión; el importador documentado sirve para el SQLite **original**. Para datos creados después del refactor, implementa un exportador del contrato de memoria antes de cambiar de entorno. El ZIP original no contenía una base real, así que la importación se probó con bases sintéticas.

## Cambios de API Python

Los nombres de archivos pedidos siguen en la raíz como fachadas; eso no significa que todas las firmas anteriores sigan siendo compatibles.

| Original | Refactor |
|---|---|
| `Memory(str_path).add(role, text)` | `SQLiteMemory(Path(path)).append_turn(user, assistant, revision)` |
| `Memory.recent(n)` | `snapshot(n).messages`, con dataclasses `Message` |
| `create_llm_client(dict, launcher, avatar)` | `create_llm_client(LLMConfig, ToolRegistry)` |
| `_process()` une GUI/LLM/memoria | `ConversationService.reply(text)` independiente de interfaz |
| Dos GUIs con persistencia distinta | Un controlador Qt, dos temas |

Se rompe deliberadamente `add()` para impedir que dos escrituras separadas dejen medio turno. No existe alias engañoso que parezca conservar esa operación.
