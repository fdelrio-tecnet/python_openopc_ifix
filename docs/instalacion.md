# Instalación y entornos

[Inicio](../README.md) · [Guía original OpenOPC](../instalacion_openopc.md)

## Estado y destino

El sistema completo todavía no se instala ni arranca: SQLite, administración y
servidor UA están planificados. Esta guía distingue requisitos de procedimientos
ejecutables. No hay un `requirements.txt` del servidor propio todavía.

Destino informado: un equipo Windows Server 2019 Datacenter 1809; todos los
procesos propios bajo el mismo usuario. No se requiere comunicación HTTP ni pipes.

## Entorno de cálculo

- Python 3.9 de **32 bits**, obligatorio por COM/OpenOPC.
- OpenOPC-DA 1.5.1 y pywin32 compatibles con ese runtime.
- Automation Wrapper x86. La guía original registra Graybox.OPC.DAWrapper.
- Servidor local `Intellution.OPCiFIX.1`.
- Entorno iFIX informado: iFIX 2023 v7 build 9737 e IGS 7.614.263.

La [guía original](../instalacion_openopc.md) conserva pasos y versiones observadas.
Revisar qué partes aplican: NumPy/Pandas aparecen en ella pero no son dependencias
del código de cálculo actual. No ejecutar registros COM o instalaciones globales
como parte de una prueba unitaria.

El `.venv` del checkout apuntaba a un Python39-32 ausente durante la revisión.
No copiar ese entorno al destino: crearlo allí con el intérprete correspondiente.
La carpeta local `openopc/` está ignorada por Git y no constituye instalación ni
dependencia reproducible incluida en un clon nuevo.

## Entorno del servidor OPC UA — planificado

Proceso y entorno virtual separados, Python x64 y biblioteca UA con versiones
fijadas después de comprobar soporte en Windows Server 2019. `asyncua` es la
alternativa evaluada, no una dependencia ya instalada/aprobada por pruebas reales.

La biblioteca compartida de almacenamiento será compatible con Python 3.9 y
usará `sqlite3`. Verificar `sqlite3.sqlite_version` en ambos runtimes; la versión
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
de base y arranque UA se agregarán cuando existan y hayan sido verificados.
