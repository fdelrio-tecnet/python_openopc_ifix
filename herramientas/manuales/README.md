# Ensayos manuales de iFIX

[Inicio](../../README.md) · [Pruebas automatizadas](../../docs/pruebas.md)

Estos programas históricos requieren OpenOPC/COM e iFIX reales. No son pruebas
unitarias ni forman parte del flujo productivo modular o del futuro servidor UA.
Se conservan para diagnóstico y pruebas controladas, sin ejecutarlos durante la
verificación automatizada del repositorio.

| Programa | Operación |
|---|---|
| `lectura_ifix.py` | Lee continuamente dos tags de prueba y muestra valores/calidad |
| `calculos_ifix.py` | Lee presiones, calcula con geometría fija y **escribe en iFIX** |

Antes de ejecutarlos, revisar servidor, host y tags definidos al inicio. El ensayo
de cálculo duplica fórmulas históricas y tolera calidad no Good; no usarlo para
validar la política del código productivo. Reservar tags de ensayo y evitar otros
escritores sobre esas mismas salidas. Ambos programas se detienen con Ctrl+C.

Usar el entorno Python 3.9 x86 descrito en [instalación](../../docs/instalacion.md).
Se movieron desde `tests/test_lectura_ifix.py` y `tests/test_calculos_ifix.py`
para separar explícitamente ejecución manual de descubrimiento automático.
