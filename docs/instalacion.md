# Instalación y entornos

[Inicio](../README.md) · [Guía original OpenOPC](referencias/instalacion_openopc.md)

## Estado y destino

El sistema completo todavía no arranca: el coordinador está pendiente.
Existen [SQLite v3](almacenamiento.md), resultados/importadores y consola de
administración, sin dependencias externas nuevas. Esta guía distingue requisitos de procedimientos
ejecutables. Existe servidor UA de ensayo con dependencias separadas.
La etapa 3a de nodos/disponibilidad también usa solo biblioteca estándar y módulos
del repositorio; no instala biblioteca UA ni necesita endpoint para sus pruebas.

Destino informado: un equipo Windows Server 2019 Datacenter 1809; todos los
procesos propios bajo el mismo usuario. No se requiere comunicación HTTP ni pipes.

## Entorno de cálculo

- Python 3.9 de **32 bits**, obligatorio por COM/OpenOPC.
- OpenOPC-DA 1.5.1 y pywin32 compatibles con ese runtime.
- Automation Wrapper x86. La guía original registra Graybox.OPC.DAWrapper.
- Servidor local `Intellution.OPCiFIX.1`.
- Entorno iFIX informado: iFIX 2023 v7 build 9737 e IGS 7.614.263.

La [guía original](referencias/instalacion_openopc.md) conserva pasos y versiones observadas.
Revisar qué partes aplican: NumPy/Pandas aparecen en ella pero no son dependencias
del código de cálculo actual. No ejecutar registros COM o instalaciones globales
como parte de una prueba unitaria.

El `.venv` del checkout apuntaba a un Python39-32 ausente durante la revisión.
No copiar ese entorno al destino: crearlo allí con el intérprete correspondiente.
La carpeta local `openopc/` está ignorada por Git y no constituye instalación ni
dependencia reproducible incluida en un clon nuevo.

## Entorno del servidor OPC UA — desarrollo verificado, destino pendiente

Esta computadora NO es el destino. Se verificó Python 3.12.14 x64 con asyncua 2.0.1
en `.venv-opcua`, separado de COM. Ver [ADR 004](decisiones/004-transporte-ua-ensayo.md).
La biblioteca requiere Python >=3.10; no instalar sus dependencias en Python 3.9 x86.
La selección todavía debe calificarse en Windows Server 2019 con IGS.

Con Python 3.12 x64 seleccionado como `python`, desde la raíz:

```console
python -m venv .venv-opcua
.venv-opcua\Scripts\python.exe -m pip install -r servidor_opcua/requirements-lock.txt
.venv-opcua\Scripts\python.exe -m pip check
```

`requirements.txt` fija la biblioteca; `requirements-lock.txt` fija la resolución
probada en desarrollo. No es una garantía de compatibilidad con el equipo de destino.
Recrear allí el entorno; no copiar venvs, rutas personales o bases sintéticas como
datos de producción. Para cambios de dependencias, repetir las dos suites y registrar
la nueva resolución. No se instala un servicio ni se modifica el firewall.
Arranque/configuración: [guía de ensayo](servidor_opcua_ensayo.md).

La biblioteca compartida de almacenamiento usa `sqlite3`, sin dependencias nuevas,
y se verifica su sintaxis Python 3.9. Falta probar el runtime x86 real.
Verificar `sqlite3.sqlite_version` en ambos runtimes; la versión
de Python no define por sí sola todas las capacidades del motor SQLite incluido.

## Rutas y permisos

- Base en disco local, no carpeta de red ni sincronizada.
- Ruta absoluta única para todos los procesos; datos y backups fuera del código.
- Cuenta con acceso al directorio de la base y archivos auxiliares WAL/SHM.
- Endpoint UA local, puerto configurable libre y configuración compatible en IGS.
- Misma cuenta no garantiza que todo software de seguridad permita el endpoint;
  verificar bajo la identidad de ejecución real.
- Registro de wrapper, instalación de servicios o cambios de políticas pueden
  requerir al administrador; no son requisitos de las pruebas documentales/locales.

## Comprobaciones no mutantes disponibles

Con el intérprete elegido, desde una consola:

```console
python -c "import sys, struct, sqlite3; print(sys.version); print(struct.calcsize('P') * 8); print(sqlite3.sqlite_version)"
```

En el proceso OpenOPC el resultado de arquitectura debe ser 32. Ver
[pruebas](pruebas.md) para comandos sin iFIX. Los comandos de creación/importación
de base están en [administración](configuracion_importaciones.md).
Antes de desplegar: verificar instalación x64, versiones SQLite de ambos procesos,
permisos de datos/WAL, puerto libre, política de seguridad y pruebas IGS/AR bajo
la cuenta real. No declarar producción aprobada por pasar las pruebas locales.
