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

## Tráfico front-back

La UI usa `ws://<host>/ws/stream` para recibir snapshots y estado del emulador. Las tablas se construyen una vez y luego solo se actualizan celdas de valor. Los controles de usuario —inputs analógicos, checkboxes de inyección digital, válvulas y botones de comando— no se reescriben por snapshot, para no pisar edición ni scroll.

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

## Escritura

La llave única de escritura real es `runtime/write_mode.txt`:

```text
read_only
```

No escribe al PLC. Registra el pedido localmente para prueba de UI/API.

```text
write_enabled
```

Permite escribir tags marcados como `writable: true`: comandos reales `cB#*` e inyecciones `y*`.


## Servicio experto de emulación

El contenedor `field-emulator` escribe inicialmente `yNvCamAsp` y `yNvRes` usando `POST /api/injection` contra el servicio web. La válvula de ingreso gobierna `yNvCamAsp`; cuanto más abierta, más rápido incrementa el nivel simulado de cámara. La válvula de salida gobierna `yNvRes`; cuanto más abierta, más rápido decrementa el nivel simulado de reserva. Las bombas aportan transferencia cámara → reserva. La salida por defecto está calibrada para que 3 bombas en marcha con válvula de reserva al 50% produzcan balance neutro en la reserva; desde ese punto, la evolución es proporcional a cantidad de bombas y apertura de válvula. Los límites se toman del snapshot: `gCamFn..gCamRb` para cámara y `gResFn..gResSp` para reserva. El dibujo web usa como feedback visible `eNvCamAsp` y `eNvRes`.


## `bB#Arndo` y generación opcional de `yB#EMar`

La lectura digital oficial de cada bomba conserva `bB#InE` e incluye `bB#Arndo` al final del paquete. El check web `generar EMar` no reemplaza el feedback: solo automatiza la escritura de `yB#EMar` hacia el controlador siguiendo `bB#Arndo`. El estado visible de proceso sigue saliendo de `bB#EMar` y del resto de lecturas genuinas.


## Logs

Los logs persistentes se escriben en `runtime/logs/` y se pueden consultar desde la web en la sección **Diagnóstico y logs** o por API:

```bash
curl http://localhost:8200/api/logs
curl "http://localhost:8200/api/logs/trasvase-tester?lines=300"
curl "http://localhost:8200/api/logs/field-emulator?lines=300"
curl http://localhost:8200/api/diagnostics
```

Archivos principales:

- `runtime/logs/trasvase-tester.log`: servidor web, master Modbus integrado, lecturas, escrituras, errores de conexión y comandos.
- `runtime/logs/field-emulator.log`: servicio experto de emulación, válvulas y escrituras de `yNvCamAsp` / `yNvRes`.
