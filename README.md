# Cálculo y publicación de linepack

Sistema Python para calcular presión promedio y linepack de tramos de gasoducto.
Las entradas se leen de iFIX mediante OpenOPC. La arquitectura acordada incorpora
SQLite local como intercambio y almacenamiento del último estado, y un servidor
OPC UA propio que publicará los resultados hacia IGS, iFIX y Operations Hub.

## Estado real — 17 de septiembre de 2026

| Componente | Estado |
|---|---|
| Parser del JSON compartido | Implementado: tramos directos y en subsistemas, IDs y salidas únicas |
| Matemática actual y predictiva | Implementada; validaciones de finitud y 72 puntos |
| Lectura/escritura OPC DA | Implementada en funciones; verificada con cliente falso |
| Pruebas automatizadas sin iFIX | 26 pruebas ejecutadas satisfactoriamente durante la última entrega de código |
| Coordinador `python_scheduler/main.py` | Stub; solo imprime `Main` |
| SQLite, esquema e importadores | Planificados; todavía no existen |
| Servidor OPC UA propio | Planificado; todavía no existe |
| Integración del nuevo flujo con IGS/iFIX | Pendiente |

Las pruebas se ejecutaron con Python 3.12 x64 y se comprobó sintaxis Python 3.9.
Esto no equivale a validar ejecución con Python 3.9 x86, COM ni iFIX.
No hay todavía un comando que arranque el sistema completo.

## Documentación

- [Arquitectura y flujo de información](docs/arquitectura.md).
- [Modelo de datos y consistencia](docs/modelo_datos.md).
- [Configuración e importaciones](docs/configuracion_importaciones.md).
- [Instalación y entornos](docs/instalacion.md).
- [Operación y recuperación](docs/operacion.md).
- [Pruebas y criterios de aceptación](docs/pruebas.md).
- [Decisión: SQLite compartido](docs/decisiones/001-sqlite-compartido.md).
- [Registro de cambios](CHANGELOG.md).
- [Reglas para modificar el proyecto](AGENTS.md).

## Código y referencias existentes

- [`python_scheduler/`](python_scheduler/README.md): parser, cálculos y comunicación OPC DA.
- [`tests/`](docs/pruebas.md): pruebas automáticas sin iFIX.
- [Herramientas manuales](herramientas/manuales/README.md): ensayos históricos con iFIX real.
- [Guía original de instalación OpenOPC](docs/referencias/instalacion_openopc.md): antecedentes de la instalación validada en otro entorno.

Las capturas históricas `tags.txt`, `arbol_ifix.json`, `arbol_ifix.txt` y la copia
`python_scheduler.zip` se retiraron del árbol activo; permanecen recuperables en Git.

El JSON compartido de tramos pertenece a otro proyecto y no se modifica.
No está incluido en este repositorio. La ruta de despliegue será configurable.

## Construcción por etapas

1. Base documental y decisiones de arquitectura: esta entrega.
2. Almacenamiento SQLite, módulo común e importaciones.
3. Servidor OPC UA con productor de prueba.
4. Integración del calculador, scheduling, observabilidad y pruebas en iFIX.

Cada etapa debe actualizar sus documentos afectados en la misma entrega.
Las etiquetas **implementado**, **planificado** y **pendiente de verificar**
describen estados diferentes; una decisión acordada no implica código ejecutable.
