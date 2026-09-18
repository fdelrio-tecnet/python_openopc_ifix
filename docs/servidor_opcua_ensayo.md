# Servidor OPC UA de ensayo — etapa 3b

[Inicio](../README.md) · [Instalación](instalacion.md) · [Contrato de publicación](publicacion_opcua.md)

## Alcance y seguridad

Implementado y probado en la computadora de desarrollo, **no en el servidor de
destino**. No conecta a iFIX, no cambia su PDB y no instala servicios ni reglas de
firewall. Lee una base SQLite v3 existente sin modificar tablas, migrar ni importar.

Solo escucha en `127.0.0.1`; puerto configurable (48410 por defecto). No hay HTTP.
El perfil exige `--ensayo-local`: anónimo, NoSecurity, sin certificados. Cualquier
proceso local con acceso al puerto puede leer; loopback no identifica al usuario.
Las variables son solo lectura y los clientes anónimos no tienen rol administrador.
Este perfil **no constituye aprobación de seguridad para producción**.

## Configuración portable

Modelo: [opcua.ejemplo.json](../configuracion/opcua.ejemplo.json). Es independiente
del JSON compartido de CamuLinepack, que no cambia.

| Opción | Contrato |
|---|---|
| `base_sqlite` | Obligatoria; absoluta o relativa al directorio del JSON, no al cwd |
| `puerto` | Entero 1–65535; ocupado implica fallo, sin elegir otro automáticamente |
| `namespace_uri` | URN estable; por defecto `urn:linepack:local` |
| `sondeo_segundos` | 0.1–60; por defecto 2, intervalo de espera entre sondeos completos |
| `vigencia_actual_segundos` | Positivo finito; por defecto 120 desde cálculo |
| `vigencia_predictiva_segundos` | Positivo finito; por defecto 1800 desde verificación |

Se rechazan claves desconocidas/duplicadas y rutas UNC. No se detectan unidades
de red mapeadas o carpetas sincronizadas: elegir explícitamente disco local.
No hay recarga del archivo en caliente. Cambiar namespace cambia la identidad de
los nodos para clientes; conservarlo al trasladar/reiniciar la instalación.

## Ejecución de ensayo

Preparar el entorno según [instalación](instalacion.md). Los comandos siguientes
son interfaces implementadas; `BASE_NUEVA_ABSOLUTA` y `CONFIG_UA` son marcadores
que deben sustituirse por rutas de ensayo elegidas por el operador. El directorio
de la base debe existir. Entrecomillar rutas con espacios.

```text
.venv-opcua\Scripts\python.exe -m servidor_opcua.productor_prueba --base BASE_NUEVA_ABSOLUTA
.venv-opcua\Scripts\python.exe -m servidor_opcua --config CONFIG_UA --ensayo-local
.venv-opcua\Scripts\python.exe -m servidor_opcua.cliente_prueba --config CONFIG_UA
```

1. El productor crea exclusivamente una base nueva con `ENSAYO-001` y geometría
   sintética; guarda resultados actuales y 72 predictivos. Nunca sobrescribe una
   base existente. Los valores predictivos son artificiales, no un pronóstico.
2. Copiar/adaptar el ejemplo de configuración para apuntar a esa base nueva.
3. Arrancar el servidor en una consola y el cliente en otra. El cliente usa por
   defecto ese tramo/base-tag; admite `--tramo-id` y `--base-tag` para otros casos.
4. Detener con Ctrl+C. El productor no es periódico: los datos vencerán si nadie
   los actualiza. No borrar una base para reutilizar este productor sobre datos reales.

El cliente imprime JSON con clave, estado UA, valor y timestamp; lee incluso
calidades Bad. No escribe nodos. Las pruebas automatizadas usan bases temporales,
puertos efímeros y cierran los servidores al finalizar.

## Contrato de transporte

Carpeta `Linepack` → carpeta por ID → tres variables. NodeId string es la clave
`tramos/<id escapado>/<sufijo>` definida en [nodos](publicacion_opcua.md).
Resolver el índice del namespace por URI; no fijar `ns=2` en clientes propios.
Nombres visibles `<base_tag>_PPROMEDIO`, `_LINEPACK` y `_LINEPACK_PRED`.
Double escalar o Double de rango 1 y dimensión 72, con unidades bar abs/Sm³ según
el contrato. El array se reemplaza como un valor completo, no punto por punto.

| Estado/motivo interno | StatusCode UA | Valor en red |
|---|---|---|
| Disponible | Good | Escalar o array redondeado |
| Vencido | UncertainLastUsableValue | Último valor íntegro |
| Sin resultado/adquisición | BadWaitingForInitialData | Null |
| Error de lectura/fuente | BadNoCommunication | Null |
| Otros no disponibles | BadOutOfService | Null |

En asyncua 2.0.1 un DataValue Bad no conserva su valor útil en el espacio de
direcciones: se publica Null deliberadamente. SQLite conserva el último estado.
El atributo DataType sigue siendo Double aunque el valor Bad sea Null. No se
publican ceros de relleno. Verificar cómo IGS/AR/iFIX representan Null y Uncertain.
`SourceTimestamp` conserva la fecha original de cálculo, `ServerTimestamp` la de
publicación; una invalidación global no representa un nuevo cálculo.

SQLite entrega snapshot coherente, pero las escrituras de variables UA son
secuenciales: **no hay atomicidad entre PPROMEDIO, LINEPACK y otros nodos**.
Tampoco se confirma recepción/persistencia en IGS por publicar correctamente.

## API y ciclo

| Archivo/API | Entradas, efectos y salida |
|---|---|
| `configuracion.cargar_configuracion(ruta)` | Lee JSON, devuelve `ConfiguracionUA`; ValueError por opciones inválidas, errores de archivo propagados; no abre SQLite |
| `adaptador.convertir_datavalue(publicacion)` | Devuelve DataValue desde publicación validada; aplica calidad/timestamps, sin acceso a SQLite |
| `AdaptadorUA.iniciar(publicaciones)` | Conjunto completo; crea nodos/calidad antes de abrir listener; propaga errores de biblioteca/puerto |
| `AdaptadorUA.publicar(publicaciones)` | Conjunto completo con mismas definiciones; muta nodos; ValueError si cambia catálogo, fallas UA propagadas |
| `AdaptadorUA.invalidar_fuente()` / `cerrar()` | Invalidan nodos / cierran transporte; async, errores propagados |
| `__main__.ejecutar(config)` | Lee snapshot, inicia y sondea hasta cancelación/falla; cierra en finally |
| `productor_prueba.crear_ensayo(base)` | Crea/escribe base nueva sintética; devuelve ruta; propaga errores, conserva base parcial ante falla para diagnóstico |
| `cliente_prueba.consultar(config, tramo_id, base_tag)` | Lectura UA de tres nodos; devuelve registros; errores de conexión/nodos propagados |

Todas las llamadas del adaptador se hacen en el mismo event loop. Cada lectura
SQLite abre/lee/cierra su conexión en el mismo worker mediante `asyncio.to_thread`;
no se comparte esa conexión entre hilos. La API pura del paquete no importa asyncua.

Ante error global tras arranque se intenta marcar todos los nodos Bad y se cierra;
no se garantiza que clientes alcancen a recibir la invalidación antes del cierre.
No hay reconexión automática. Altas o cambios de nombres requieren reinicio; una
inactivación con identidad intacta se refleja en disponibilidad. CLI: salida 0 por
Ctrl+C, 1 por fallo operativo y 2 por argumentos inválidos. Log básico de consola,
sin rotación ni estadísticas persistentes.

## Límites y siguiente parte

Cada sondeo lee todo el snapshot, reevalúa vencimientos y republica todos los nodos.
El trabajo crece con tramos × 72, incluso sin cambios; no es todavía la estrategia
incremental definitiva. No hay mediciones de carga representativa ni garantías de
CPU/memoria/latencia en destino. El intervalo de 2 s no es una frecuencia garantizada:
se suma tiempo de lectura y publicación. No se crean hilos ni procesos por tramo.

Etapa 3c: consulta incremental con caché coherente y vencimiento periódico,
recuperación acotada, pruebas de fallas prolongadas y calificación IGS/AR en el
servidor real autorizado. Antes del despliegue confirmar versiones, puerto libre,
permisos locales, política de seguridad, mapeo de calidad/arrays y consumo. La
integración del calculador con SQLite sigue siendo una etapa separada.
