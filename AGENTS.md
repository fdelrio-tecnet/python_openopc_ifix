# Reglas de mantenimiento del proyecto

Estas instrucciones aplican a todo el repositorio. Lea primero `README.md` y
los documentos relevantes de `docs/` antes de modificar código.

## Restricciones y contratos

- Conservar Python 3.9 de 32 bits para el proceso OpenOPC/COM. No introducir
  sintaxis o dependencias incompatibles en ese proceso ni en módulos compartidos.
- El servidor OPC UA tiene su propio entorno; no imponer sus dependencias al
  proceso de cálculo. Python 3.12 x64/asyncua se verificaron en desarrollo;
  la calificación en el equipo de destino sigue pendiente. Ver docs/instalacion.md.
- No modificar el JSON de tramos compartido con CamuLinepack. Adaptar el lector.
- Conservar fórmulas, unidades y `PI_SOBRE_4 = 0.785398` salvo cambio explícitamente
  acordado y acompañado de análisis de impacto.
- Usar `CANTIDAD_PUNTOS_PREDICCION` compartida. PPROMEDIO_PRED es entrada absoluta.
- Exigir Good por defecto y mantener la opción explícita de desactivarlo.
- Mantener cálculos independientes de OpenOPC, JSON y SQLite.
- Toda la arquitectura inicial es local, en un equipo y con un mismo usuario.
  SQLite es el intercambio acordado; no agregar HTTP, pipes o acceso remoto sin
  una decisión de arquitectura nueva.
- Preservar cambios existentes del usuario. No conectar ni escribir en iFIX
  durante pruebas unitarias; la integración requiere un entorno de ensayo autorizado.

## Documentación obligatoria por entrega

Actualizar documentación junto con cualquier cambio relevante:

| Cambio | Documentos afectados |
|---|---|
| Flujo, responsabilidades o dependencias | `docs/arquitectura.md` y su diagrama |
| Esquema, consistencia o migraciones | `docs/modelo_datos.md` |
| JSON, comandos o reglas de importación | `docs/configuracion_importaciones.md` |
| Versiones, dependencias o despliegue | `docs/instalacion.md` |
| Arranque, fallas, logs, backups | `docs/operacion.md` |
| Pruebas, cobertura o requisitos de validación | `docs/pruebas.md` |
| Estado general o cambio visible | `README.md`, `CHANGELOG.md` |
| Decisión arquitectónica significativa | Registro nuevo en `docs/decisiones/` |

- Diferenciar implementado, planificado y pendiente de verificar en el equipo real.
- Documentar funciones públicas: entradas, salidas, unidades, efectos y excepciones.
- Mantener una fuente principal por tema y enlazarla; evitar copias divergentes.
- Los comandos presentados como ejecutables deben existir y haberse comprobado.
  Identificar expresamente ejemplos o interfaces propuestas.
- Cambios de esquema deben incluir estrategia para bases existentes, backup y
  compatibilidad entre procesos. No destruir ni recrear una base real por defecto.
- No registrar secretos, rutas personales como valores de producción ni mediciones
  estimadas como si fueran resultados de pruebas.

## Verificación y cierre

- Ejecutar pruebas pertinentes sin iFIX y comprobar compatibilidad Python 3.9
  de los módulos afectados. Aclarar si no se dispone del intérprete x86 real.
- Para documentación: revisar enlaces locales, comandos, nombres y coherencia
  con el código. No ejecutar scripts manuales OPC como si fueran tests unitarios.
- Informar cambios, pruebas realizadas, documentos actualizados y limitaciones.
- Una entrega no está completa si su documentación relevante quedó desactualizada.
