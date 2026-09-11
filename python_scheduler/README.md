# Sistema de Cálculo de Linepack para iFIX

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

La arquitectura base se considera definida y operativa.