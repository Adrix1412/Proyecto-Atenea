# Atenea — Fase 2: diario persistente de tareas

`SqliteTaskJournal` registra cada solicitud antes de invocar la acción, identificada por `request_id` y huella de la solicitud exacta. La reserva es atómica con SQLite (`BEGIN IMMEDIATE` y clave primaria). Una solicitud repetida no vuelve a ejecutar el handler. `TaskExecutor(journal)` autoriza, reserva, ejecuta y guarda el resultado; `ToolRegistry.execute_authorized(..., journal=journal)` permite usar la misma vía con herramientas tipadas. El llamador conserva la responsabilidad de autenticar actor y dispositivo.

Al iniciar el diario, las tareas que quedaron en `RUNNING` pasan a `UNKNOWN`; pueden haber producido un efecto antes de la caída. La operación no se reintenta automáticamente. Si falla la reserva, no se invoca el handler; si falla guardar el resultado, la respuesta es `UNKNOWN` y el registro pendiente se recuperará como `UNKNOWN` tras reiniciar. `get(request_id)` permite consultar estado y mensaje. Los tokens de aprobación nunca se almacenan: reiniciar los revoca.

## Límite de esta fase

- **Un solo proceso dueño por archivo de SQLite**. Inicializar otro diario mientras el primero está ejecutando marca equivocadamente sus tareas activas como `UNKNOWN`. Aún no existe coordinación distribuida, arrendamiento, cola remota ni detección de procesos vivos. No conectar esta ruta a Android ni a un servidor con varios trabajadores.
- No hay garantía de ejecución exactamente una vez frente a efectos externos; `UNKNOWN` exige verificación humana o reconciliación específica antes de cualquier nueva solicitud. No hay política de retención ni cifrado del diario; elegir un directorio privado del usuario y evitar argumentos sensibles al usarlo.
- Esta fase no conecta automáticamente el escritorio existente al diario; la ruta nueva requiere pasar explícitamente `journal` a la llamada autorizada. La ruta local antigua sigue sin persistencia.

Verificación en este entorno: 73 pruebas, Ruff y mypy (42 archivos fuente). Las pruebas nuevas incluyen reinicio con tarea en curso, fallo de almacenamiento antes de invocar el handler, reserva concurrente y bloqueo de repetición de tareas completadas o inciertas. No se ejecutaron aplicaciones Windows reales.

## Explicación clave

- [Seguro] Un ID repetido se reserva una vez y la acción no se reejecuta mediante este diario.
- [Seguro] Una tarea en curso durante un reinicio queda `UNKNOWN` y requiere comprobación antes de actuar de nuevo.
- [Suponiendo] El uso local tiene un solo proceso dueño del archivo SQLite; para varios trabajadores se requiere coordinación adicional.
