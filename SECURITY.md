# Seguridad y límites del refactor

## Correcciones aplicadas

| Hallazgo original | Cambio | Riesgo concreto reducido |
|---|---|---|
| `shell=True` para comandos string | Listas fijas, rutas absolutas, `shell=False`, rechazo de scripts/shells | Interpretación de metacaracteres por el sistema |
| Tool calling con validación mínima | Registro cerrado, argumentos exactos, catálogo, límites y confirmación | Ejecución fuera de capacidades autorizadas |
| API key guardada por ambas GUIs | Lectura del entorno, campos extra rechazados | Publicación accidental de credenciales |
| Excepciones del proveedor mostradas literalmente | Errores seguros y logs de metadatos | Fuga de cuerpos HTTP y datos sensibles |
| Token VTS dentro del repositorio | Directorio de datos del usuario y escritura atómica | Inclusión accidental del token en Git |
| Memoria global sin propietarios | Conversaciones con propietario y comprobación en vista/repositorio | Acceso cruzado entre usuarios web |
| Dos escrituras para cada turno | Transacción única con revisión esperada | Historial incompleto o sobrescritura concurrente |
| Audio y bucles sin límites suficientes | Duración/tamaño/rondas acotados; limpieza de temporales | Consumo de memoria y ejecución indefinida por iteración |

Las configuraciones se consideran administración local de confianza. La lista de ejecutables no es una sandbox: alguien que pueda editar la configuración o sustituir un binario ya tiene capacidad de ejecutar programas bajo esa cuenta. Los argumentos son fijos y el modelo solo elige un alias. Revisa el catálogo y el comando mostrado en cada confirmación.

Los prompts y resultados web pueden contener instrucciones hostiles. El texto del system prompt no constituye una barrera de seguridad; las restricciones reales son la validación de argumentos, el registro de capacidades y la confirmación independiente. El modelo todavía puede equivocarse al responder: una fuente citada por el modelo no constituye verificación automática de su afirmación.

Los secretos permanecen en el entorno del proceso y pueden ser accesibles a software con privilegios suficientes. El token VTS y la memoria no están cifrados. `chmod(0600)` protege en sistemas POSIX; en Windows protege la carpeta mediante ACL de tu usuario. Los logs no registran mensajes, claves ni resultados de búsquedas; la ventana/terminal sí muestra la conversación.

No se incluyen `.env`, `config.yaml`, contraseñas, claves reales, tokens VTS ni bases con conversaciones. Si un secreto fue publicado antes en otro repositorio, borrarlo en este refactor no lo revoca: rótalo en el proveedor y revisa el historial Git.

No hay revisión de seguridad externa ni garantía de ausencia total de vulnerabilidades. Los límites pendientes de producción web (caché compartido, cuotas y autenticación anfitriona) están explicados en `docs/DJANGO.md`.
