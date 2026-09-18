# Pruebas y verificación

[Inicio](../README.md) · [Instalación](instalacion.md)

## Pruebas automáticas existentes

Desde la raíz, con un Python disponible:

```console
python -m unittest discover -s tests -p test_parse_config_json.py -v
python -m unittest discover -s tests -p test_escritura_predicciones.py -v
python -m unittest discover -s tests -p test_ciclo_opc.py -v
```

No requieren OpenOPC instalado, iFIX ni pytest. Las pruebas de comunicación cargan
el módulo con OpenOPC falso; no abren conexiones reales.

| Archivo | Casos | Cobertura principal |
|---|---:|---|
| `test_parse_config_json.py` | 10 | Ambas ubicaciones, duplicados, validación, tags, 72 puntos y estados independientes |
| `test_escritura_predicciones.py` | 9 | Respuestas parciales/duplicadas/ajenas, lotes, errores globales y reintentos |
| `test_ciclo_opc.py` | 7 | Flujo actual/predictivo, Good configurable, no finitos, F_00/F_71 y estado tras fallas |
| `test_almacenamiento.py` | 13 | Creación exclusiva, persistencia, versión, rollback/COMMIT fallido, lectura protegida, snapshot y bloqueo entre conexiones |
| `test_importaciones.py` | 12 | Cargas completas, versiones, discordancias, rollback, validación y migración v1 con backup |
| `test_repositorio.py` | 19 | Paquetes, CAS, precisión, firmas, rollback, adquisición, snapshots concurrentes, dos procesos, migración v2 y CLI |

Última entrega de código: 70 pruebas satisfactorias con Python 3.12 x64 y análisis
de sintaxis Python 3.9. No es validación del runtime Python 3.9 x86 ni de COM.
El número es una referencia de esa entrega: actualizar al cambiar la suite.

Los programas manuales se encuentran en
[`herramientas/manuales/`](../herramientas/manuales/README.md), fuera de `tests/`.
Requieren OpenOPC real y uno escribe resultados. No ejercitan el flujo SQLite/UA.
Para ejecutar toda la suite automática desde la raíz:

```console
python -m unittest discover -s tests -v
```

## Almacenamiento e importaciones: cobertura y pendientes

Infraestructura 2a verificada con archivos temporales y conexiones independientes
en un proceso. Etapa 2b verifica importaciones y backup de migración en archivos
temporales. Etapa 2c agrega concurrencia de dos procesos y snapshots frente a un
escritor. Faltan ensayos prolongados, recuperación operativa y medidas
en el equipo de destino. Ver [alcance de la API](almacenamiento.md).

- Verificado: JSON válido/inválido, duplicados de miembros y magnitudes no finitas.
- Verificado: catálogo y geometría dispares sin rechazo global.
- Verificado: altas, cambios, inactivaciones y reimportación idéntica.
- Verificado: fallo a mitad de importación conserva la versión anterior completa.
- Verificado: pareja actual y serie de 72 no quedan parcialmente reemplazadas.
- Verificado: cambio de geometría/catálogo rechaza cálculo obsoleto.
- Verificado: reintento, ID reutilizado con otro contenido y paquete retrasado.
- Verificado: dos procesos escritores compiten por revisión; bloqueos con conexiones independientes.
- Verificado: snapshot/revisiones sin omisiones al escribir durante consultas.
- Base reabierta conserva último estado, esquema incompatible se rechaza.
- Backup/restauración consistente y reinicio de cursores.
- Ejecutar bajo ambos runtimes y versiones SQLite seleccionadas.

## Etapa servidor UA sin iFIX

- Productor falso guarda en SQLite; cliente UA lee escalares y arrays.
- NodeIds estables después de reiniciar o ampliar catálogo.
- Arranque sin resultados no publica ceros válidos.
- Geometría vigente distinta invalida resultados anteriores.
- Predicción verificada sin cambios no vence por antigüedad del cálculo.
- Vencimientos detectados aunque no haya escrituras a SQLite.
- Publicación fallida se reintenta sin saltar revisión.
- Reinicio mientras el productor sigue activo recupera último estado.
- Medir memoria, CPU, latencia y duración con carga representativa; distinguir
  resultados medidos de estimaciones.

## Integración con IGS/iFIX — pendiente

- Endpoint local y usuario real; confianza/certificados/política UA según lo elegido.
- Mapear nombres existentes PDB a nodos UA estables.
- Probar array de 72 hacia AR, orden y extremos 0/71.
- Verificar calidad de no disponible/desactualizado en iFIX y Operations Hub.
- Leer las entradas OPC DA y comprobar unidades/Good.
- Validar resultados conocidos: 44.66/44.31 barg, 6 in, 4 mm, 10000 m producen
  aproximadamente 45.498474367603876 bar abs y 7993.124399335523 Sm³.
- Reiniciar productor, publicador e IGS por separado y ensayar indisponibilidad.
- Prueba prolongada con carga habitual del equipo, registrando memoria, CPU,
  duración de ciclos, bloqueos y retraso hasta iFIX.

## Verificación documental

Revisar enlaces locales, nombres y comandos. Mantener el diagrama Mermaid junto
con los cambios de flujo. Antes de declarar una etapa operativa, contrastar cada
afirmación con código/pruebas y marcar las limitaciones del entorno utilizado.
