# Frontera de emulación

## Criterio operativo

El tester lee y presenta las cuatro tablas SCA del intercambio de producción:

| Índice | Tabla SCA | Tipo Modbus | Rango leído | Uso visible |
|---:|---|---|---:|---|
| 0 | `SCA - lectura AN [0]` | input register | `30001..30026` | lecturas analógicas reales |
| 1 | `SCA - consigna AN [1]` | holding register | `42049..42083` | consignas y readback de inyección |
| 2 | `SCA - lectura DI [2]` | input status | `14097..14173` | lecturas digitales reales |
| 3 | `SCA - comando DI [3]` | coil | `6145..6187` | comandos y readback de inyección |

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

Las áreas `y*` son memoria de escritura hacia el controlador y no representan el proceso: el estado oficial se toma de `e*` y `b*` del intercambio genuino. Sin embargo, FC03 y FC01 vuelven a leer también las posiciones `y*` para confirmar la imagen de intercambio que conserva el PLC y evitar que la UI muestre una orden local como si ya hubiera sido aplicada.

La lectura digital incluye `bResFR` en fila 4, referencia `14101`. Es un bit de lógica positiva: confirma reserva fuera de rango cuando el nivel es menor que `gResFn` o mayor que `gResSp`; la igualdad con cualquiera de los límites sigue siendo una lectura sana.

Ubicación vigente de inyección:

- Consignas analógicas: último valor real fila `21`; filas `22..26` libres; `yNvCamAsp` inicia en fila `27`, ref `42076`; `yB5Hs` termina en fila `34`, ref `42083`.
- Comandos digitales: último valor real fila `17`; filas `18..22` libres; `yRFF` inicia en fila `23`, ref `6168`; `yB5Falla` termina en fila `42`, ref `6187`.

## Escritura e inyección

Las consignas `g*` y los comandos `c*` enviados por un operador que ingresó desde `edge-platform` se encolan siempre para escritura al PLC. No dependen del polling FC01..FC04 ni de una habilitación adicional.

Los comandos `cB#Aut` y `cB#Mr` son bits mantenidos por el controlador: una acción genera una única escritura de `0` o `1`, sin reafirmación periódica. Todos los bits del intercambio usan lógica positiva; un valor `1` confirma el estado expresado por el nombre del tag.

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

El contenedor `field-emulator` escribe inicialmente `yNvCamAsp` y `yNvRes` usando `POST /api/injection` contra el servicio web. La válvula de ingreso gobierna `yNvCamAsp`; cuanto más abierta, más rápido incrementa el nivel simulado de cámara. El consumo horario decrementa `yNvRes` y las bombas efectivamente en marcha aportan transferencia cámara → reserva. Cada bomba aporta `12 mm/s`; el consumo máximo es `45,6 mm/s`, equivalente a 3,8 bombas. Cuatro bombas superan entonces el pico del 100% por `2,4 mm/s`, un margen del 5%. El consumo conserva sus picos, valles y transiciones cosenoidales suaves según la hora simulada. El ingreso estacional a cámara mantiene una tasa máxima independiente de `45 mm/s`.

El emulador no decide ningún arranque, parada, selección ni rotación. Solo cuenta `bB1EMar..bB5EMar` leídos del controlador; la quinta bomba aporta al modelo exclusivamente cuando el controlador confirma `bB5EMar=1`. La cola conserva un único valor pendiente por nivel sin cambiar su orden y mantiene aparte la operación Modbus en curso, por lo que ambos tags conservan su turno aunque lleguen muestras nuevas. Los límites se toman del snapshot: `gCamFn..gCamRb` para cámara y `gResFn..gResSp` para reserva. El dibujo web usa como feedback visible `eNvCamAsp` y `eNvRes`.


## Controles compartidos de bomba

La selectora Tablero/RTU y el grupo de radios `generar EMar` no mantienen estado en el navegador. La selectora envía `yB#RTU` y representa su readback por FC01; el indicador `RTU` representa por separado el estado de campo `bB#RTU` leído por FC02. El modo EMar pertenece a `RuntimeState` y `PumpControlStore`; las selecciones solicitadas se respaldan en `runtime/pump_controls.json`. El snapshot y el WebSocket comparten los valores con todos los clientes y el navegador no los reemplaza con estado propio.

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
