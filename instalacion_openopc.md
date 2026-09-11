# Instalación y puesta en marcha de OpenOPC con iFIX

## Objetivo

Esta guía documenta los pasos que se utilizaron correctamente para instalar y configurar **OpenOPC-DA** en un entorno con:

- Windows de 64 bits.
- Python 3.9 de 32 bits.
- iFIX 2023, versión 7, build 9737.
- Industrial Gateway OPC Server 7.614.263.
- Servidor OPC DA de iFIX: `Intellution.OPCiFIX.1`.

El objetivo final es poder leer y escribir campos de tags de la base de datos de iFIX desde Python mediante OpenOPC.

---

## 1. Requisitos de arquitectura

En este entorno fue necesario usar Python de **32 bits** por compatibilidad con OPC DA, COM y los componentes utilizados por iFIX.

La combinación utilizada fue:

```text
Sistema operativo: Windows 64 bits
Python:            3.9 de 32 bits
OpenOPC-DA:        1.5.1
pywin32:           312
Pyro5:             5.17
Wrapper OPC DA:    Graybox.OPC.DAWrapper de 32 bits
Servidor OPC iFIX: Intellution.OPCiFIX.1
```

Es importante que Python, `pywin32` y el Automation Wrapper COM sean compatibles con 32 bits.

---

## 2. Crear y activar el entorno virtual

Desde PowerShell, ubicarse en la carpeta del proyecto:

```powershell
cd "C:\Users\PC-ING-001\Desktop\9479\pruebas_openopc"
```

Crear el entorno virtual con el ejecutable de Python de 32 bits:

```powershell
python -m venv .venv
```

Activarlo:

```powershell
.\.venv\Scripts\Activate.ps1
```

El prompt debería quedar parecido a:

```text
(.venv) PS C:\Users\PC-ING-001\Desktop\9479\pruebas_openopc>
```

---

## 3. Verificar que Python sea de 32 bits

Ejecutar:

```powershell
python -c "import struct; print(struct.calcsize('P') * 8)"
```

El resultado esperado es:

```text
32
```

También puede verificarse con:

```powershell
python -c "import platform; print(platform.architecture())"
```

Resultado esperado:

```text
('32bit', 'WindowsPE')
```

---

## 4. Actualizar las herramientas de instalación

Dentro del entorno virtual:

```powershell
python -m pip install --upgrade pip setuptools wheel
```

---

## 5. Instalar OpenOPC y sus dependencias

Instalar la distribución utilizada:

```powershell
python -m pip install OpenOPC-DA
```

Esto instala también las dependencias principales, entre ellas `pywin32` y `Pyro5`.

Verificar la instalación:

```powershell
python -m pip show OpenOPC-DA
python -m pip list | Select-String -Pattern "OpenOPC|pywin32|Pyro"
```

En el entorno probado se obtuvo:

```text
OpenOPC-DA      1.5.1
Pyro5           5.17
pywin32         312
```

Puede aparecer también `Pyro4`. No es necesario para la conexión COM local utilizada en esta prueba. OpenOPC-DA 1.5.1 utiliza `Pyro5` para sus funciones de gateway.

---

## 6. Instalar NumPy y Pandas en Python 3.9 de 32 bits

Las versiones actuales de Pandas pueden no ofrecer un wheel para Python 3.9 de 32 bits. En ese caso, `pip` intenta compilar Pandas y falla por falta de herramientas de Visual Studio.

El síntoma observado fue la descarga de un archivo como:

```text
pandas-2.3.3.tar.gz
```

seguida de un error relacionado con Meson y `vswhere.exe`.

Para evitar compilación local, se fijaron versiones compatibles:

```powershell
python -m pip install numpy==1.26.4
python -m pip install pandas==1.5.3
```

También puede hacerse en una sola operación:

```powershell
python -m pip install numpy==1.26.4 pandas==1.5.3
```

Verificación:

```powershell
python -c "import numpy, pandas; print(numpy.__version__); print(pandas.__version__)"
```

> Nota: NumPy y Pandas no son necesarios para establecer la comunicación OPC básica. Se instalaron para futuros cálculos, almacenamiento y procesamiento de datos.

---

## 7. Verificar que el servidor OPC DA de iFIX esté registrado

El ProgID utilizado por iFIX fue:

```text
Intellution.OPCiFIX.1
```

Para comprobar su registro:

```powershell
reg query HKCR\Intellution.OPCiFIX.1
```

La salida obtenida fue:

```text
HKEY_CLASSES_ROOT\Intellution.OPCiFIX.1
    (Predeterminado)    REG_SZ    OPC Data Access 2.0 Server for iFix

HKEY_CLASSES_ROOT\Intellution.OPCiFIX.1\CLSID
```

Esto confirma que el servidor OPC DA de iFIX está instalado y registrado.

---

## 8. Resolver el error `Dispatch: Cadena clase no válida`

### 8.1 Síntoma

Al ejecutar:

```python
import OpenOPC

opc = OpenOPC.client()
```

se obtuvo:

```text
OpenOPC.OPCError: Dispatch: Cadena clase no válida
```

El código de error COM era:

```text
-2147221005
```

### 8.2 Causa

OpenOPC estaba instalado, pero Windows no tenía registrado un **OPC DA Automation Wrapper** compatible.

El servidor OPC DA de iFIX y el Automation Wrapper son componentes diferentes:

```text
OpenOPC
   ↓
OPC DA Automation Wrapper
   ↓
Intellution.OPCiFIX.1
   ↓
Base de datos de iFIX
```

No era necesario buscar un wrapper específico de iFIX. Se necesitaba un wrapper OPC DA genérico.

---

## 9. Obtener el Automation Wrapper

El paquete instalado mediante `pip` no incluía la DLL. Esto se verificó con:

```powershell
python -m pip show -f OpenOPC-DA
```

En la lista de archivos no aparecieron:

```text
gbda_aut.dll
opcdaauto.dll
```

Se obtuvo el repositorio correspondiente a OpenOPC y se utilizó la DLL:

```text
gbda_aut.dll
```

La ruta utilizada fue:

```text
C:\Users\PC-ING-001\Desktop\9479\pruebas_openopc\openopc\lib\gbda_aut.dll
```

La DLL registra la clase COM:

```text
Graybox.OPC.DAWrapper
```

> Usar solamente una DLL obtenida del repositorio oficial o de otra fuente confiable. No descargar DLL COM desde sitios desconocidos.

---

## 10. Verificar que `gbda_aut.dll` sea de 32 bits

Como no se disponía de `dumpbin`, se leyó la cabecera PE desde PowerShell.

```powershell
$dll = "C:\Users\PC-ING-001\Desktop\9479\pruebas_openopc\openopc\lib\gbda_aut.dll"

$stream = [System.IO.File]::OpenRead($dll)
$reader = New-Object System.IO.BinaryReader($stream)

try {
    $stream.Position = 0x3C
    $peOffset = $reader.ReadInt32()

    $stream.Position = $peOffset
    $signature = $reader.ReadUInt32()

    if ($signature -ne 0x00004550) {
        Write-Host "El archivo no tiene una cabecera PE válida." -ForegroundColor Red
        return
    }

    $machine = $reader.ReadUInt16()

    switch ($machine) {
        0x014C {
            Write-Host "La DLL es de 32 bits (x86)." -ForegroundColor Green
        }
        0x8664 {
            Write-Host "La DLL es de 64 bits (x64)." -ForegroundColor Yellow
        }
        0x01C0 {
            Write-Host "La DLL es ARM de 32 bits." -ForegroundColor Yellow
        }
        0xAA64 {
            Write-Host "La DLL es ARM64." -ForegroundColor Yellow
        }
        default {
            Write-Host ("Arquitectura no reconocida. Machine: 0x{0:X4}" -f $machine) -ForegroundColor Red
        }
    }
}
finally {
    $reader.Close()
    $stream.Close()
}
```

Para el entorno utilizado, el resultado requerido era:

```text
La DLL es de 32 bits (x86).
```

El código PE correspondiente a x86 es:

```text
0x014C
```

---

## 11. Registrar el wrapper de 32 bits

Abrir PowerShell o Símbolo del sistema **como administrador**.

En Windows de 64 bits, una DLL COM de 32 bits debe registrarse con el `regsvr32` ubicado en `SysWOW64`:

```powershell
& "C:\Windows\SysWOW64\regsvr32.exe" "C:\Users\PC-ING-001\Desktop\9479\pruebas_openopc\openopc\lib\gbda_aut.dll"
```

El resultado esperado es:

```text
DllRegisterServer se realizó correctamente
```

Aunque el nombre pueda resultar confuso:

```text
C:\Windows\SysWOW64\regsvr32.exe  → componentes COM de 32 bits
C:\Windows\System32\regsvr32.exe → componentes COM de 64 bits
```

---

## 12. Verificar el registro del wrapper

Ejecutar:

```powershell
reg query HKCR\Graybox.OPC.DAWrapper
```

También puede comprobarse directamente desde Python:

```python
import win32com.client

wrapper = win32com.client.Dispatch("Graybox.OPC.DAWrapper")
print("Wrapper OPC creado correctamente:", wrapper)
```

Si esta prueba funciona, el error `Cadena clase no válida` quedó resuelto.

---

## 13. Enumerar servidores OPC DA desde OpenOPC

Prueba utilizada:

```python
import OpenOPC

opc = OpenOPC.client()

try:
    print(opc.servers())
finally:
    opc.close()
```

La salida obtenida fue:

```python
[
    'Intellution.OPCiFIX.1',
    'Intellution.IntellutionGatewayOPCServer',
    'Intellution.iFixOPCClient',
    'Intellution.OPCEDA.3'
]
```

Para acceder a la base de datos de proceso de iFIX se utilizó:

```text
Intellution.OPCiFIX.1
```

---

## 14. Probar la conexión con iFIX

Antes de ejecutar la prueba deben estar activos iFIX y su base de datos de proceso.

```python
import OpenOPC

opc = OpenOPC.client()

try:
    opc.connect("Intellution.OPCiFIX.1", "localhost")
    print("Conexión exitosa con iFIX")
    print(opc.info())
finally:
    opc.close()
```

---

## 15. Explorar los tags publicados por iFIX

El servidor de iFIX respondió de esta forma:

```python
opc.list("*", recursive=False, flat=False)
```

Resultado:

```python
['FIX']
```

En cambio, la consulta recursiva devolvió todos los Item IDs:

```python
items = opc.list(
    "*",
    recursive=True,
    include_type=True,
)
```

Ejemplo de resultado:

```python
[
    ('FIX.PRUEBA_ARRAY.A_ALMACK', 'Leaf'),
    ('FIX.PRUEBA_ARRAY.A_CV', 'Leaf'),
    ('FIX.PRUEBA_ARRAY.A_DESC', 'Leaf'),
]
```

Para este servidor, la estrategia más efectiva fue:

1. Ejecutar una única consulta con `recursive=True`.
2. Recibir los Item IDs completos.
3. Extraer el primer elemento de cada tupla.
4. Reconstruir localmente la jerarquía separando cada Item ID por `.`.

Ejemplo mínimo:

```python
import OpenOPC

opc = OpenOPC.client()

try:
    opc.connect("Intellution.OPCiFIX.1")

    items = opc.list(
        "*",
        recursive=True,
        include_type=True,
    )

    print(f"Cantidad: {len(items)}")

    for item_id, item_type in items[:20]:
        print(item_id, item_type)
finally:
    opc.close()
```

---

## 16. Nomenclatura de tags iFIX

Los Item IDs del servidor OPC DA de iFIX siguen esta estructura:

```text
NODO.TAG.CAMPO
```

En el entorno probado:

```text
FIX.PRUEBA_OPC_PE.F_CV
FIX.PRUEBA_OPC_PS.F_CV
```

Campos habituales:

```text
F_CV   Valor actual numérico
A_CV   Valor actual en formato texto
A_DESC Descripción
```

Para bloques analógicos se utilizó `F_CV`.

---

## 17. Lectura simple de tags

```python
import OpenOPC

TAGS = [
    "FIX.PRUEBA_OPC_PE.F_CV",
    "FIX.PRUEBA_OPC_PS.F_CV",
]

opc = OpenOPC.client()

try:
    opc.connect("Intellution.OPCiFIX.1")

    resultados = opc.read(TAGS)

    for nombre, valor, calidad, timestamp in resultados:
        print(nombre, valor, calidad, timestamp)
finally:
    opc.close()
```

Formato típico devuelto por una lectura múltiple:

```python
[
    ('FIX.PRUEBA_OPC_PE.F_CV', 44.66, 'Good', timestamp),
    ('FIX.PRUEBA_OPC_PS.F_CV', 44.31, 'Good', timestamp),
]
```

---

## 18. Lectura periódica

Para mantener una conexión activa y leer cada 30 segundos:

```python
import time
import OpenOPC

TAGS = [
    "FIX.PRUEBA_OPC_PE.F_CV",
    "FIX.PRUEBA_OPC_PS.F_CV",
]

opc = OpenOPC.client()

try:
    opc.connect("Intellution.OPCiFIX.1")

    while True:
        resultados = opc.read(TAGS)

        for nombre, valor, calidad, timestamp in resultados:
            print(nombre, valor, calidad, timestamp)

        time.sleep(30)
finally:
    opc.close()
```

Para una aplicación permanente conviene incluir reconexión automática y reutilizar la misma conexión mientras esté activa.

---

## 19. Escritura de tags

OpenOPC acepta una tupla para una escritura individual:

```python
resultado = opc.write(
    ("FIX.PRUEBA_OPC_PPROMEDIO.F_CV", 45.498)
)
```

Para escribir varios tags en una sola llamada se utiliza una lista de tuplas:

```python
escrituras = [
    ("FIX.PRUEBA_OPC_PPROMEDIO.F_CV", 45.498),
    ("FIX.PRUEBA_OPC_LINEPACK.F_CV", 7993.12),
]

resultado = opc.write(escrituras)
print(resultado)
```

El tipo de `escrituras` es conceptualmente:

```python
list[tuple[str, float]]
```

La respuesta puede ser:

```python
[
    ('FIX.PRUEBA_OPC_PPROMEDIO.F_CV', 'Success'),
    ('FIX.PRUEBA_OPC_LINEPACK.F_CV', 'Success'),
]
```

Siempre conviene leer los valores después de escribir para confirmar que la escritura persistió:

```python
print(
    opc.read([
        "FIX.PRUEBA_OPC_PPROMEDIO.F_CV",
        "FIX.PRUEBA_OPC_LINEPACK.F_CV",
    ])
)
```

---

## 20. Consideraciones sobre bloques AI de salida

Para las pruebas se utilizaron bloques de tipo `AI` en iFIX.

Una escritura a `F_CV` puede ser aceptada por OPC, pero si el bloque está `On Scan` y asociado a un driver, el driver puede sobrescribir inmediatamente el valor.

También debe revisarse el rango configurado. Por ejemplo:

```text
PPROMEDIO esperado: aproximadamente 45 bar abs
LINEPACK esperado:  aproximadamente 8000 Sm3
```

Rangos de prueba razonables:

```text
PRUEBA_OPC_PPROMEDIO: 0 a 100
PRUEBA_OPC_LINEPACK:  0 a 20000
```

Si `opc.write()` devuelve `Error` para LINEPACK, revisar primero:

- rango de ingeniería;
- límites del bloque;
- tipo de bloque;
- capacidad de escritura;
- estado On Scan / Off Scan;
- asociación con el driver IGS;
- existencia de otro proceso que actualice el mismo tag.

Para resultados calculados externamente, es preferible utilizar bloques que no sean sobrescritos por un driver de entrada.

---

## 21. Varios clientes OpenOPC simultáneos

Es posible conectar varios clientes OpenOPC al mismo servidor:

```text
Intellution.OPCiFIX.1
```

Recomendaciones:

- Se permiten múltiples lectores.
- Mantener un solo escritor por tag.
- Cada proceso debe crear su propio objeto `OpenOPC.client()`.
- No compartir un mismo objeto OpenOPC entre procesos.
- Evitar compartir la misma conexión COM entre hilos.
- Mantener la comunicación OPC en un único hilo por cliente.
- Cerrar siempre la conexión con `opc.close()`.

---

## 22. Diagnóstico rápido

### Error: `Dispatch: Cadena clase no válida`

Causa probable:

```text
Automation Wrapper COM ausente o no registrado
```

Verificar:

```powershell
reg query HKCR\Graybox.OPC.DAWrapper
```

Probar:

```python
import win32com.client
win32com.client.Dispatch("Graybox.OPC.DAWrapper")
```

### `opc.servers()` no incluye iFIX

Verificar:

```powershell
reg query HKCR\Intellution.OPCiFIX.1
```

Revisar que iFIX y sus componentes OPC estén instalados.

### La lectura devuelve calidad `Error` o `Bad`

Revisar:

- Item ID exacto.
- Base de datos de iFIX cargada.
- Bloque existente.
- Campo correcto, normalmente `F_CV`.
- Estado de iFIX y del driver.

### La escritura devuelve `Success`, pero el valor no se ve

Causa probable:

```text
El driver vuelve a sobrescribir el F_CV del bloque AI
```

Probar temporalmente con el bloque `Off Scan` y leer inmediatamente después de escribir.

### La escritura devuelve `Error`

Revisar:

- rango del bloque;
- valor fuera de escala;
- permisos de escritura;
- tipo de bloque;
- campo destino;
- configuración del driver.

### Pandas intenta compilarse y falla

Usar versiones compatibles con Python 3.9 de 32 bits:

```powershell
python -m pip install numpy==1.26.4 pandas==1.5.3
```

---

## 23. Prueba integral mínima

Este programa verifica wrapper, conexión, listado y lectura:

```python
import OpenOPC

OPC_SERVER = "Intellution.OPCiFIX.1"

TAGS = [
    "FIX.PRUEBA_OPC_PE.F_CV",
    "FIX.PRUEBA_OPC_PS.F_CV",
]

opc = OpenOPC.client()

try:
    print("Servidores OPC disponibles:")

    for servidor in opc.servers():
        print(f"  {servidor}")

    print(f"\nConectando con {OPC_SERVER}...")
    opc.connect(OPC_SERVER, "localhost")

    print("Conexión establecida.\n")

    resultados = opc.read(TAGS)

    for nombre, valor, calidad, timestamp in resultados:
        print(
            f"{nombre}: "
            f"valor={valor}, "
            f"calidad={calidad}, "
            f"timestamp={timestamp}"
        )
finally:
    opc.close()
    print("\nConexión OPC cerrada.")
```

---

## 24. Checklist final

- [ ] Python 3.9 de 32 bits instalado.
- [ ] Entorno virtual activado.
- [ ] `OpenOPC-DA` instalado.
- [ ] `pywin32` instalado.
- [ ] `Pyro5` instalado.
- [ ] `gbda_aut.dll` verificada como x86.
- [ ] `gbda_aut.dll` registrada con `SysWOW64\regsvr32.exe`.
- [ ] `Graybox.OPC.DAWrapper` visible en el registro.
- [ ] `Intellution.OPCiFIX.1` visible en el registro.
- [ ] `OpenOPC.client()` crea el cliente sin errores.
- [ ] `opc.servers()` muestra `Intellution.OPCiFIX.1`.
- [ ] iFIX está iniciado y la base de datos está cargada.
- [ ] `opc.connect("Intellution.OPCiFIX.1")` funciona.
- [ ] Los Item IDs se validaron con `recursive=True`.
- [ ] Las lecturas devuelven calidad `Good`.
- [ ] Las escrituras se verifican mediante una lectura posterior.
- [ ] Los bloques de salida tienen rangos suficientes.
- [ ] Ningún driver sobrescribe involuntariamente los valores calculados.

---

## Resultado final

La cadena de comunicación que quedó operativa fue:

```text
Servidor OPC UA de prueba
        ↓
Industrial Gateway OPC Server
        ↓
iFIX Process Database
        ↓
Servidor OPC DA Intellution.OPCiFIX.1
        ↓
Graybox OPC DA Automation Wrapper de 32 bits
        ↓
OpenOPC-DA en Python 3.9 de 32 bits
```

Con esta configuración fue posible:

- descubrir el servidor OPC DA de iFIX;
- conectarse desde Python;
- navegar los Item IDs publicados;
- leer PE y PS periódicamente;
- realizar cálculos externos;
- intentar escribir resultados en campos `F_CV` de la base de datos de iFIX.
