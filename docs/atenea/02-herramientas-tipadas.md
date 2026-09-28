# Atenea — avance de Fase 2: contratos tipados de herramientas

Se añadió `TypedTool[ArgsT]` al Core sin quitar el adaptador `Tool` anterior. Las composiciones de escritorio y Django ya registran búsqueda con `SearchArgs`; escritorio registra también `OpenAppArgs` y `ExpressionArgs`. Cada clase Pydantic prohíbe propiedades desconocidas y la validación es estricta. El esquema público sale de `model_json_schema()` y el registro añade las opciones permitidas de las herramientas con catálogo local.

Orden de ejecución: **esquema → valores permitidos y dominio → autorización → efecto**. Una acción que necesita confirmación no puede registrarse sin callback de autorización. Si falla el callback o el handler, el registro devuelve un error genérico y no muestra la excepción al LLM. Se conserva el límite de resultado de 6000 caracteres y los límites de rondas por turno del cliente existente. `Tool` admite herramientas antiguas mientras se migren otras capacidades.

## Evidencia

- 61 pruebas automatizadas; se añadieron casos de modelo con dos campos, datos faltantes o extra, tipo incorrecto, rechazo de dominio, denegación, fallo de política, confirmación de apertura y presencia del esquema en payloads Ollama/Anthropic/Gemini simulados.
- mypy Core y escritorio y Ruff correctos en este entorno; sin llamadas a APIs reales ni acciones reales de dispositivo.

## Alcance de esta entrega

La confirmación de `abrir_app` sigue siendo la pregunta local por CLI/GUI. **No es** una aprobación persistente vinculada a identidad, dispositivo, argumentos y vencimiento. No existe aún un `TaskExecutor` duradero ni un `PermissionEngine` para agentes remotos. No conectar estas tools directamente a WebSockets o Android antes de implementar esas piezas.

Para seguir: modelar identidad/permiso por solicitud y aprobación de uso único, ejecutar con timeout/cancelación, persistir estado de tareas y probar reintentos sin efectos duplicados. La compatibilidad efectiva de los esquemas con modelos de proveedor en vivo está pendiente.

## Explicación clave

- [Seguro] Validar el JSON del modelo antes de consultar permisos impide que campos desconocidos lleguen a una acción.
- [Seguro] Una respuesta del LLM nunca constituye autorización; la decide un callback del sistema.
- [Seguro] El contrato actual permite varios campos sin eliminar los handlers antiguos de un campo durante la migración.
