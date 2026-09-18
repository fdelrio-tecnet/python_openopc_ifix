# ADR 004 — transporte OPC UA local de ensayo

Estado: adoptado para desarrollo; calificación en destino pendiente.

## Contexto

El equipo de desarrollo no es Windows Server 2019 de destino. OpenOPC mantiene
Python 3.9 x86 y no debe heredar dependencias UA. El intercambio acordado es SQLite.

## Decisión

Usar [FreeOpcUa/opcua-asyncio](https://github.com/FreeOpcUa/opcua-asyncio), paquete
`asyncua==2.0.1`, en entorno separado. Verificado aquí con Python 3.12.14 x64.
[Metadatos de la versión](https://pypi.org/project/asyncua/2.0.1/) requieren Python
>=3.10; no instalarlo en el proceso COM. Fijar resolución de dependencias de ensayo
en requirements-lock.txt y recrear el entorno en destino, nunca copiar el venv.

Primer transporte limitado a loopback, anónimo sin cifrado con opción explícita
de ensayo, variables de solo lectura y sin autoridad administrativa para clientes.
No adoptar implícitamente este perfil para producción. Namespace estable, NodeIds
string por ID/sufijo, arrays de 72 y calidad explícita, pendientes de validar en IGS.

## Consecuencias

Permite validar transporte sin iFIX ni credenciales/configuración del servidor real.
El primer sondeo es completo y las fallas globales cierran el proceso; la recuperación
e incrementalidad quedan para 3c. Los resultados Bad se exponen Null y no cero.
La atomicidad SQLite no se extiende entre nodos UA. No cambia el esquema v3.

Referencias: [ensayo y límites](../servidor_opcua_ensayo.md),
[instalación](../instalacion.md), [pruebas](../pruebas.md).
