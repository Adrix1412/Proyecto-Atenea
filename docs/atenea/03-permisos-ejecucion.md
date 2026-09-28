# Atenea — avance de Fase 2: aprobaciones y ejecutor local

El Core incorpora `ActionRequest`, `PermissionEngine` y `TaskExecutor`. Una solicitud lleva ID de petición, identidad del actor, dispositivo, capacidad, argumentos JSON y nivel de riesgo. La aprobación se emite **solo tras confirmación por una interfaz confiable**. El token dura como máximo cinco minutos, está ligado a todos esos campos y se consume una sola vez bajo un bloqueo de concurrencia. El nivel `EXTERNAL` está deshabilitado.

`ToolRegistry.execute_authorized` ofrece una vía separada para llamadas que ya han autenticado al actor y al dispositivo. Solo acepta `TypedTool`: comprueba capacidad, riesgo, igualdad exacta de argumentos, esquema y dominio antes de consumir la aprobación. El callback local de la herramienta se evalúa antes de consumirla. `TaskExecutor` devuelve `SUCCEEDED`, `DENIED` o `UNKNOWN`; si el handler falla después de recibir autorización, `UNKNOWN` no justifica repetir automáticamente una acción que puede haber ocurrido.

## Límites actuales

- La identidad indicada en `ActionRequest` todavía procede del código llamador. **No hay autenticación de agentes ni endpoint remoto**; jamás exponer `issue` al LLM, Android o un cliente HTTP.
- Las aprobaciones están en memoria del proceso. Reiniciar revoca todas; no hay coordinación entre varios servidores ni una cola de tareas.
- `ToolRegistry.execute` conserva el comportamiento local anterior para el escritorio y no debe usarse como endpoint remoto. La ruta autorizada es `execute_authorized`.
- No hay límite temporal ni cancelación de un handler bloqueante. La ejecución autorizada es síncrona; la persistencia, el estado `UNKNOWN` duradero, la recuperación y la idempotencia de tareas pertenecen a la siguiente fase.
- La comprobación de esquemas publicados a Ollama, Anthropic y Gemini usa fixtures simuladas; queda pendiente una prueba con modelos reales.
- Avatar/expresiones sigue siendo una capacidad cosmética local. No se publica como acción remota hasta fijar una política de presencia.

## Pruebas y reversión

En este entorno pasaron 69 pruebas, Ruff, mypy (41 archivos fuente) y las comprobaciones de Django. La suite incluye expiración, token de uso único bajo concurrencia, cambio de argumentos, dispositivo, actor, capacidad, ID, riesgo y errores que podrían ocurrir tras un efecto. Para repetir: `pytest -q`, `ruff check .`, `ruff format --check .` y `mypy alicia_core alicia_desktop`. Para revertir, usa el ZIP anterior `Atenea_Fase2_Herramientas_Tipadas.zip`; no hay migración de base de datos ni credenciales guardadas.

## Explicación clave

- [Seguro] La aprobación exacta de una acción no autoriza otra con distintos argumentos o dispositivo.
- [Seguro] Un error después de invocar una herramienta deja incierto si hubo efecto; repetir sin comprobar puede duplicarlo.
- [Seguro] Esta versión demuestra el contrato local de autorización, pero todavía no proporciona control remoto seguro ni tareas persistentes.
