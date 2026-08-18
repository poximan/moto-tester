# Frontera de emulación

## Criterio operativo

El tester lee y presenta las cuatro tablas SCA del intercambio de producción:

| Índice | Tabla SCA | Tipo Modbus | Rango leído | Uso visible |
|---:|---|---|---:|---|
| 0 | `SCA - lectura AN [0]` | input register | `30001..30026` | lecturas analógicas reales |
| 1 | `SCA - consigna AN [1]` | holding register | `42049..42070` | consignas reales |
| 2 | `SCA - lectura DI [2]` | input status | `14097..14173` | lecturas digitales reales |
| 3 | `SCA - comando DI [3]` | coil | `6145..6162` | comandos reales |

En la UI, las cuatro tablas SCA muestran solo tags de producción. Se respetan las filas internas vacías del intercambio real, pero no se muestra la zona `y*` dentro de esas cuatro tablas.

Las teclas FC01..FC04 de la cabecera gobiernan únicamente las lecturas y la actualización de pantalla. Cada una nace activa a 2000 ms y conserva su habilitación y período en `runtime/modbus_polling.json`. Las consultas se inician desfasadas y sus errores se registran por separado, de modo que una respuesta inválida no interrumpe las demás tablas. Las escrituras FC05/FC06 son independientes: `g*`, `c*` y el control dedicado `yB#EMar` se escriben siempre; las demás inyecciones `y*` dependen del modo de inyección.

## Tráfico front-back

La UI usa `ws://<host>/ws/stream` para recibir snapshots y estado del emulador. Las tablas se construyen una vez y luego solo se actualizan celdas de valor. Los controles de usuario —inputs analógicos, checkboxes de inyección digital, válvulas y botones de comando— no se reescriben por snapshot, para no pisar edición ni scroll.

La cápsula `Fuente` identifica si los valores visibles provienen del PLC configurado —incluye host e ID— o del simulador local. Es información de procedencia; no es una llave operativa.

## Inyección

No existen tablas de fachada separadas. Las señales `y*` entran por las tablas escribibles, pero conceptualmente pisan señales de lectura:

| Tabla de inyección en UI | Entra por | Pisa internamente |
|---|---|---|
| Inyección de lecturas analógicas | `SCA - consigna AN [1]` / holding register / FC06 | `SCA - lectura AN [0]` / input register |
| Inyección de lecturas digitales | `SCA - comando DI [3]` / coil / FC05 | `SCA - lectura DI [2]` / input status |

Las áreas `y*` son solo memoria de escritura hacia el controlador; no se leen para representar el proceso. La lectura de estado oficial se toma de `e*` y `b*` del intercambio genuino.

Ubicación vigente de inyección:

- Consignas analógicas: último valor real fila `21`; filas `22..26` libres; `yNvCamAsp` inicia en fila `27`, ref `42076`; `yB5Hs` termina en fila `34`, ref `42083`.
- Comandos digitales: último valor real fila `17`; filas `18..22` libres; `yRFF` inicia en fila `23`, ref `6168`; `yB5Falla` termina en fila `42`, ref `6187`.

## Escritura e inyección

Las consignas `g*` y los comandos `c*` enviados por un operador que ingresó desde `edge-platform` se encolan siempre para escritura al PLC. No dependen del polling FC01..FC04 ni de una habilitación adicional.

El modo persistente gobierna los pedidos genéricos de inyección `y*`. `runtime/injection_mode.txt` conserva el último estado elegido a través de sesiones web y reinicios. El control dedicado `generar EMar` es una excepción explícita y no consulta este modo:

```text
disabled
```

Omite los pedidos genéricos de inyección `y*`. No altera la posibilidad de escribir `g*`, `c*` o el control dedicado `yB#EMar`.

```text
enabled
```

Permite escribir los tags de inyección `y*` por la API genérica. El estado no vence ni se reinicia automáticamente; permanece `enabled` hasta que un operador seleccione `disabled` desde la interfaz web. El ingreso operativo se realiza sin login a través de la ruta pública de `edge-platform`.


## Servicio experto de emulación

El contenedor `field-emulator` escribe inicialmente `yNvCamAsp` y `yNvRes` usando `POST /api/injection` contra el servicio web. La válvula de ingreso gobierna `yNvCamAsp`; cuanto más abierta, más rápido incrementa el nivel simulado de cámara. La válvula de salida gobierna `yNvRes`; cuanto más abierta, más rápido decrementa el nivel simulado de reserva. Las bombas aportan transferencia cámara → reserva. La salida por defecto está calibrada para que 3 bombas en marcha con válvula de reserva al 50% produzcan balance neutro en la reserva; desde ese punto, la evolución es proporcional a cantidad de bombas y apertura de válvula. Los límites se toman del snapshot: `gCamFn..gCamRb` para cámara y `gResFn..gResSp` para reserva. El dibujo web usa como feedback visible `eNvCamAsp` y `eNvRes`.


## Controles compartidos de bomba

La selectora Tablero/RTU y el grupo de radios `generar EMar` no mantienen estado en el navegador. Sus fuentes de verdad son respectivamente `yB#RTU` y el modo EMar dentro de `RuntimeState`, con respaldo en `runtime/pump_controls.json`; el snapshot y el WebSocket comparten el mismo valor con todos los clientes y el backend lo recupera después de reiniciarse.

Cada cambio de `generar EMar` se encola directamente sobre su tag. **Deshabilitado** impone `yB#EMar=0`, **Forzar** impone `yB#EMar=1` y **Automático** copia `bB#Arndo`: `1` cuando está activo y `0` en caso contrario. El servidor vuelve a escribir los valores persistidos al arrancar y reafirma la salida en cada actualización de `bB#Arndo`; la política no depende del modo general de inyección. La tabla y la API genérica de inyección no permiten modificar `yB#EMar`, evitando una segunda fuente de verdad.


## Logs

Los logs persistentes se escriben en `runtime/logs/` y se pueden consultar desde la web en la sección **Diagnóstico y logs** o por API:

```bash
curl https://comunicaciones.servicoop.com.ar/moto-tester/api/logs
curl "https://comunicaciones.servicoop.com.ar/moto-tester/api/logs/trasvase-tester?lines=300"
curl "https://comunicaciones.servicoop.com.ar/moto-tester/api/logs/field-emulator?lines=300"
curl https://comunicaciones.servicoop.com.ar/moto-tester/api/diagnostics
```

Archivos principales:

- `runtime/logs/trasvase-tester.log`: servidor web, master Modbus integrado, lecturas, escrituras, errores de conexión y comandos.
- `runtime/logs/field-emulator.log`: servicio experto de emulación, válvulas y escrituras de `yNvCamAsp` / `yNvRes`.
