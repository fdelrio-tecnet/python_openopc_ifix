# Sistema de Cálculo de Linepack para iFIX

> Alcance de este documento: módulos existentes de cálculo y OPC DA. El punto de
> entrada continúa como stub; no hay servicio completo ejecutable. La arquitectura
> objetivo utiliza SQLite compartido (catálogo/geometrías ya implementados) y un
> servidor OPC UA propio todavía pendiente. Consultar el [README principal](../README.md) y el
> [flujo actualizado](../docs/arquitectura.md) como fuentes del estado general.
> Las descripciones de publicación directa en iFIX de este documento corresponden
> a las funciones OPC DA existentes, no a la integración futura SQLite/UA.

## Objetivo

Este programa calcula y publica en iFIX:

- Presión promedio (`PPROMEDIO`)
- Linepack actual (`LINEPACK`)
- Linepack predictivo (`LINEPACK_PRED`)

a partir de información obtenida mediante OpenOPC.

La aplicación está diseñada para ejecutarse de forma continua y desacoplada de iFIX desde el punto de vista de los cálculos. Todos los valores del proceso son leídos desde OPC, procesados en Python y posteriormente escritos nuevamente en iFIX.

El diseño del sistema separa claramente:

1. Configuración.
2. Comunicación OPC.
3. Cálculos.
4. Coordinación general.

Esta separación permite modificar la lógica matemática sin afectar la comunicación OPC y viceversa.

---

# Arquitectura general

El sistema se compone actualmente de cuatro módulos principales.

```text
main.py
│
├── parse_config_json.py
├── opc_link.py
└── calculos.py
```

## Responsabilidades

### parse_config_json.py

Responsable exclusivamente de la configuración.

Lee el archivo JSON y construye la estructura interna utilizada por el resto de la aplicación.

No realiza:

- lecturas OPC;
- escrituras OPC;
- cálculos;
- lógica de ejecución.

Su única responsabilidad es transformar el JSON en una estructura consistente y validada.

El JSON compartido se conserva sin cambios. El parser reúne tramos de
`sistemas[...].tramos` y de `sistemas[...].subsistemas[...].tramos` en un
diccionario plano indexado por ID. Un sistema puede contener cualquiera de
las dos colecciones o ambas; las colecciones vacías son válidas.
`sistemas` es un objeto, mientras que `subsistemas` y `tramos` son listas.
Los subsistemas deben contener la clave `tramos`.

Los IDs duplicados se rechazan globalmente después de quitar espacios
externos. También se rechazan salidas OPC duplicadas (incluidas las
predictivas), comparadas sin distinguir mayúsculas. Las entradas compartidas
entre tramos están permitidas. Los campos adicionales del JSON se ignoran.

Las pruebas del parser verifican ambas ubicaciones, validaciones, tags,
72 puntos predictivos y estados independientes. Se ejecutan desde la raíz
del repositorio, sin OpenOPC ni iFIX, usando la biblioteca estándar:

```console
python -m unittest discover -s tests -p test_parse_config_json.py -v
```

Este comando selecciona únicamente las pruebas del parser. Los programas de
ensayo con iFIX real están separados en
[`herramientas/manuales/`](../herramientas/manuales/README.md).

---

### opc_link.py

Responsable exclusivamente de la comunicación con OpenOPC.

Incluye:

- conexión;
- desconexión;
- lectura de variables actuales;
- lectura de variables predictivas;
- escritura de resultados actuales;
- escritura de resultados predictivos.

No contiene fórmulas de ingeniería.

No realiza cálculos de presión promedio ni de linepack.

---

### calculos.py

Responsable exclusivamente de los cálculos.

Todas las funciones de ingeniería se encuentran en este módulo.

No conoce:

- OpenOPC;
- iFIX;
- nombres de tags;
- archivos JSON.

Recibe estructuras de datos ya cargadas y devuelve resultados calculados.

---

### main.py

Responsable de coordinar el funcionamiento completo del sistema.

Actualmente aún no implementado.

Será quien decida:

- cuándo leer;
- cuándo calcular;
- cuándo escribir;
- cuándo reconectar;
- cuándo ejecutar la lógica predictiva.

---

# Filosofía de diseño

Una decisión importante del proyecto es que ningún módulo intenta hacer trabajo ajeno.

Por ejemplo:

## opc_link.py

Puede leer:

```text
Presión ingreso
Presión egreso
```

pero no calcula:

```text
Presión promedio
```

porque esa responsabilidad corresponde a `calculos.py`.

---

## calculos.py

Puede calcular:

```text
Linepack
```

pero nunca escribirá:

```text
LINEPACK.F_CV
```

porque esa responsabilidad corresponde a `opc_link.py`.

---

## main.py

Es el único módulo que conoce el flujo completo de trabajo.

Por este motivo:

- la reconexión OPC se implementará en `main.py`;
- los intervalos de ejecución estarán en `main.py`;
- la coordinación entre ciclos actuales y predictivos estará en `main.py`.

---

# Estructura del proyecto

```text
proyecto/
│
├── main.py
│
├── calculos.py
│
├── opc_link.py
│
├── parse_config_json.py
│
├── configuracion.json
│
└── README.md
```

---

# Flujo de datos actual

Actualmente el flujo diseñado para los cálculos actuales es el siguiente:

```text
iFIX
 │
 ▼

Presión Ingreso
Presión Egreso
Diámetro
Espesor
Longitud

 │
 ▼

leer_datos_tramos()

 │
 ▼

Estructura interna "tramos"

 │
 ▼

calcular_todos_los_tramos()

 │
 ▼

Presión Promedio
Linepack

 │
 ▼

escribir_resultados_tramos()

 │
 ▼

iFIX
```

---

# Flujo de datos predictivo

La predicción posee una frecuencia diferente y una estructura distinta.

El programa NO calcula las presiones promedio predichas.

Esas presiones son generadas externamente y almacenadas en iFIX.

Python solamente las consume.

```text
PPROMEDIO_PRED.F_00
...
PPROMEDIO_PRED.F_71
```

son entradas del sistema.

A partir de esos valores se calculan:

```text
LINEPACK_PRED.F_00
...
LINEPACK_PRED.F_71
```

---

## Flujo predictivo

```text
iFIX

PPROMEDIO_PRED

 │
 ▼

leer_predicciones_tramos()

 │
 ▼

Detección de cambios

 │
 ▼

calcular_predicciones_todos_los_tramos()

 │
 ▼

LINEPACK_PRED

 │
 ▼

escribir_predicciones_tramos()

 │
 ▼

iFIX
```

---

# Estructura principal de datos

El programa utiliza una única estructura maestra llamada:

```python
tramos
```

La misma contiene toda la información necesaria para leer, calcular y escribir.

Conceptualmente:

```python
tramos = {

    "037-001-A": {

        "id": "...",

        "base_tag": "...",

        "tags": {...},

        "datos": {...}
    }

}
```

---

# Sección tags

Contiene exclusivamente Item IDs OPC.

Nunca contiene valores numéricos.

Ejemplo:

```python
"tags": {

    "presion_ingreso":
        "FIX....",

    "presion_egreso":
        "FIX....",

    "diametro":
        "FIX....",

    "ppromedio":
        "FIX....",

    "linepack":
        "FIX...."
}
```

---

# Sección datos

Contiene exclusivamente valores dinámicos.

Ejemplo:

```python
"datos": {

    "presion_ingreso": 45.2,
    "presion_egreso": 44.8,

    "presion_promedio": 45.0,

    "linepack": 8000.4,

}
```

Esto evita que los módulos deban reconstruir tags constantemente.

---

# Predicciones

Cada tramo posee actualmente una estructura predictiva compuesta por 72 puntos.

Los puntos corresponden a:

```text
F_00
F_01
...
F_71
```

Cada punto almacena:

```python
{
    "indice": 0,
    "campo": "F_00",

    "presion_promedio": None,

    "linepack": None,

    "valido": False,

    "error": None,
}
```

---

# Detección de cambios

La lógica predictiva incorpora detección de cambios para evitar cálculos innecesarios.

La comparación se realiza utilizando una firma.

## Firma

La firma contiene los 72 valores predictivos truncados a dos decimales.

Ejemplo:

```text
45.129 → 45.12
```

Internamente se almacena como entero:

```text
4512
```

para evitar problemas de precisión de punto flotante.

---

## Objetivo

Evitar:

```text
Leer
Calcular
Escribir
```

cada vez que se ejecuta el ciclo predictivo.

Si las predicciones no cambiaron, el cálculo no se ejecuta.

---

# Control de versiones predictivas

Cada tramo mantiene:

```python
ultima_firma
```

y

```python
firma_pendiente
```

## ultima_firma

Representa la última predicción procesada correctamente.

Es decir:

```text
Leída
Calculada
Escrita
```

sin errores.

---

## firma_pendiente

Representa una lectura nueva aún no consolidada.

La promoción:

```text
firma_pendiente
    ↓
ultima_firma
```

ocurre solamente después de una escritura exitosa.

Esto evita perder una predicción cuando la escritura falla.

---

# Manejo de errores

Las lecturas actuales y predictivas exigen calidad `Good` por defecto.
Se puede pasar `exigir_calidad_good=False` para aceptar otras calidades;
esa opción no permite valores no numéricos, booleanos, NaN o infinitos.
La política se configura al llamar a las funciones, sin modificar el JSON
compartido de tramos.

La cantidad predictiva se centraliza en `constantes.py` como
`CANTIDAD_PUNTOS_PREDICCION = 72`. El parser mantiene disponible ese nombre
por compatibilidad. Lectura, cálculo y escritura usan la misma constante;
el cálculo no depende del parser JSON ni de OpenOPC.

Antes de cada lectura predictiva se limpian presiones y linepacks,
`calculada`, timestamps, firma pendiente y estado de escritura, conservando
`ultima_firma`. Así, incluso una excepción global no deja resultados de un
ciclo anterior disponibles como actuales. Si no hay cambio, no se calcula
ni escribe y `calculada` permanece en False. Una lectura incompleta invalida
la serie; un error matemático de un punto permite calcular los otros 71,
pero nunca marca la serie como completamente calculada.

Las pruebas integradas usan un cliente falso para el flujo completo,
calidades, valores no finitos, 72 puntos, cambios en los extremos y reintentos:

```console
python -m unittest discover -s tests -p test_ciclo_opc.py -v
```

La estrategia elegida es:

```text
Error local
↓
Continuar
```

Ejemplos:

- un tramo inválido no detiene los demás;
- una predicción inválida no detiene las demás;
- un punto predictivo inválido no detiene los demás puntos.

La aplicación intentará continuar procesando la mayor cantidad posible de información.

---

# Constantes de ingeniería

Actualmente se utilizan los mismos parámetros presentes en la versión Visual Basic.

```text
π / 4 = 0.785398

Presión atmosférica = 1.01325 bar

Presión estándar = 1.01325 bar abs

Temperatura estándar = 288.15 K

Temperatura del gas = 288.15 K

Factor Z = 0.92
```

---

# Funcionalidad implementada

## Configuración

- Validación del JSON.
- Construcción de tags.
- Construcción de estructuras.
- Validación de duplicados.

## Comunicación OPC

- Conexión.
- Desconexión.
- Lectura actual.
- Escritura actual.
- Lectura predictiva.
- Escritura predictiva.

## Ingeniería

- Conversión de presiones.
- Presión promedio.
- Cálculo geométrico.
- Volumen interno.
- Linepack actual.
- Linepack predictivo.

## Predicciones

- Lectura de 72 puntos.
- Firma.
- Comparación.
- Detección de cambios.
- Control de procesamiento.

---

# Estado interno de un tramo

Conceptualmente, cada tramo mantiene tres grandes grupos de información:

```text
Tramo
│
├── Identificación
├── Tags OPC
└── Datos dinámicos
```

Ejemplo simplificado:

```python
{
    "id": "037-001-A",

    "base_tag": "SYS_037_001_A",

    "tags": {...},

    "datos": {
        ...
    }
}
```

---

## Estado actual

Dentro de `datos` se almacenan:

```python
{
    "presion_ingreso": None,
    "presion_egreso": None,
    "diametro": None,
    "espesor": None,
    "longitud": None,

    "presion_promedio": None,
    "linepack": None,

    "valido": False,
    "error": None,
    "timestamp": None,
}
```

La sección:

```python
valido
```

representa el estado de lectura y cálculo actual.

---

## Estado de escritura actual

La escritura de resultados se mantiene separada del estado de cálculo.

```python
"escritura": {

    "exitosa": False,

    "ppromedio": None,

    "linepack": None,

    "error": None,

    "timestamp": None,
}
```

Esto permite distinguir claramente entre:

```text
Error de cálculo
```

y

```text
Error de escritura OPC
```

---

## Estado predictivo

Cada tramo dispone de una sección predictiva independiente.

```python
"prediccion": {

    "puntos": [...],

    "ultima_firma": None,

    "firma_pendiente": None,

    "cambio_detectado": False,

    "calculada": False,

    "timestamp_lectura": None,

    "timestamp_calculo": None,

    "error": None,

    "escritura": {
        ...
    }
}
```

---

# Filosofía de la detección de cambios

Las predicciones de presión promedio tienen una frecuencia de actualización muy inferior a la de los datos de proceso.

Por este motivo no tiene sentido recalcular constantemente:

```text
72 linepacks
```

si las presiones promedio predictivas permanecen iguales.

Para resolver esto se implementó un mecanismo de firmas.

---

## Primera lectura

La primera vez que se leen predicciones:

```python
ultima_firma = None
```

Por lo tanto:

```python
cambio_detectado = True
```

y la predicción se procesa.

---

## Lecturas posteriores

Se compara:

```python
ultima_firma
```

contra:

```python
firma_pendiente
```

La comparación se interrumpe al detectar la primera diferencia.

```text
F_00 distinto
↓
fin de comparación
↓
cambio_detectado = True
```

Esto reduce la cantidad de operaciones cuando existen cambios tempranos en la serie.

---

# Escrituras predictivas

La escritura valida exactamente 72 puntos, 72 tags correspondientes a
`F_00`–`F_71` y una firma pendiente de 72 posiciones. Los linepacks deben
ser numéricos finitos. `tamano_lote` permite dividir cada tramo en llamadas
de tamaño limitado; `None` envía los 72 puntos juntos.

Cada lote debe devolver una única respuesta `Success` por tag enviado.
Se toleran diferencias de orden y mayúsculas. Las respuestas faltantes,
duplicadas, desconocidas, malformadas o `Error` impiden consolidar la firma.
Una respuesta de otro lote no completa un resultado faltante.
Los errores de respuesta se registran y se continúa con los demás tramos;
las excepciones de `opc.write()` se propagan al coordinador.

`puntos_exitosos` cuenta tags confirmados una sola vez; `puntos_fallidos`
cuenta los puntos enviados que no quedaron confirmados, incluidos faltantes
y ambiguos. Una respuesta extra puede invalidar el intento incluso con
72 puntos confirmados y cero puntos fallidos: el detalle queda en `error`.
Si falla una llamada, los puntos todavía no confirmados también se cuentan
como fallidos, sin afirmar que el servidor no los haya escrito.

Ante un intento incompleto se conserva `ultima_firma`, la firma pendiente
y el cambio detectado, para reintentar los 72 puntos en el próximo ciclo.
Esta confirmación indica aceptación OPC; no incluye readback.

Pruebas con cliente falso, sin OpenOPC ni iFIX, desde la raíz:

```console
python -m unittest discover -s tests -p test_escritura_predicciones.py -v
```

La escritura predictiva posee una condición adicional.

No alcanza con que exista una nueva lectura.

Además debe existir una predicción completamente calculada.

```text
cambio_detectado = True
```

y

```text
calculada = True
```

Solo entonces se publican:

```text
LINEPACK_PRED.F_00
...
LINEPACK_PRED.F_71
```

---

## Consolidación de una predicción

Una predicción nueva solamente se considera procesada cuando:

```text
Lectura OK
↓
Cálculo OK
↓
Escritura OK
```

Recién en ese momento se ejecuta:

```text
firma_pendiente
    ↓
ultima_firma
```

Esta decisión evita perder información cuando ocurre una falla después de la lectura.

---

# Funcionalidad prevista y aún no implementada

## main.py

Pendiente implementar completamente.

Será el punto de entrada de la aplicación.

Tendrá la responsabilidad de coordinar:

- configuración;
- conexión OPC;
- lectura;
- cálculos;
- escritura;
- reconexión;
- logging.

---

## Scheduler

La aplicación deberá ejecutar dos ciclos independientes.

---

### Ciclo actual

Frecuencia prevista:

```text
30 segundos
```

Responsabilidades:

```text
leer datos actuales
↓
calcular
↓
escribir resultados
```

---

### Ciclo predictivo

Frecuencia prevista:

```text
600 segundos
(10 minutos)
```

Responsabilidades:

```text
leer predicciones
↓
detectar cambios
↓
calcular
↓
escribir
```

---

## Reconexión automática

Actualmente prevista pero aún no implementada.

Objetivo:

```text
Error OpenOPC
↓
cerrar conexión
↓
esperar
↓
reconectar
↓
reanudar servicio
```

sin intervención manual.

---

## Logging

Pendiente implementar.

Se prevé utilizar el módulo estándar:

```python
logging
```

para registrar:

- inicio y fin del programa;
- conexión y reconexión;
- duración de ciclos;
- errores de lectura;
- errores de cálculo;
- errores de escritura;
- cambios detectados en predicciones.

---

## Estadísticas operativas

Pendiente implementar.

Información prevista:

```text
Cantidad de tramos válidos

Cantidad de tramos inválidos

Cantidad de predicciones nuevas

Errores de lectura

Errores de cálculo

Errores de escritura

Duración de cada ciclo
```

---

# Flujo operativo previsto (versión final)

El comportamiento esperado del programa una vez implementado `main.py` es:

```text
Inicio
│
├── Leer configuración JSON
│
├── Construir estructura de tramos
│
├── Conectar a OpenOPC
│
└── Loop principal
     │
     ├── ¿Toca ciclo actual?
     │       │
     │       ├── leer_datos_tramos()
     │       ├── calcular_todos_los_tramos()
     │       └── escribir_resultados_tramos()
     │
     ├── ¿Toca ciclo predictivo?
     │       │
     │       ├── leer_predicciones_tramos()
     │       ├── calcular_predicciones_todos_los_tramos()
     │       └── escribir_predicciones_tramos()
     │
     ├── ¿Hubo error OPC?
     │       │
     │       ├── cerrar_opc()
     │       ├── esperar
     │       └── reconectar
     │
     └── Dormir unos segundos
```

---

# Estado actual del proyecto

La lógica de negocio principal ya se encuentra implementada.

El sistema posee actualmente:

✅ Configuración y validación de tramos  
✅ Construcción automática de tags  
✅ Lectura OPC actual  
✅ Escritura OPC actual  
✅ Lectura predictiva  
✅ Detección de cambios  
✅ Cálculo de presión promedio  
✅ Cálculo de linepack actual  
✅ Cálculo de linepack predictivo  
✅ Escritura de linepack predictivo  

El trabajo pendiente se concentra principalmente en la capa de ejecución:

- implementación de `main.py`;
- scheduler;
- reconexión automática;
- logging;
- pruebas en entorno real.

Las funciones base están implementadas y verificadas con clientes falsos. La
integración operativa y la nueva arquitectura SQLite/OPC UA permanecen pendientes;
ver el [estado del proyecto](../README.md).
## Integración con almacenamiento SQLite

El parser exporta `construir_estructura_tramos(configuracion)` para validar un
objeto JSON ya leído, además de `cargar_estructura_tramos(ruta_json)`. Los
importadores SQLite reutilizan esa función tras una lectura estricta que detecta
miembros JSON duplicados, sin releer ni modificar el archivo compartido.
Ver [importaciones](../docs/configuracion_importaciones.md). El calculador aún
no lee geometría ni guarda resultados en SQLite; `main.py` sigue siendo un stub.
