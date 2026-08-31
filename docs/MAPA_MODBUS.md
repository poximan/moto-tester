# Mapa Modbus

Modo de direccionamiento: `modicon_reference`. Las referencias verificadas se calculan con la fórmula ACE3600 `offset + Z*2048 + X*256 + Y`; en este intercambio se usa `X=0`. Luego se convierten internamente a PDU cero-based.


## Fórmula ACE3600 validada

| Tabla | Kind | Z | X | Primera fila/ref | Última fila/ref | PDU primera | PDU última |
|---|---|---:|---:|---:|---:|---:|---:|
| `SCA - lectura AN [0]` | input register | 0 | 0 | 0 / 30001 | 25 / 30026 | 0 | 25 |
| `SCA - consigna AN [1]` | holding register | 1 | 0 | 0 / 42049 | 34 / 42083 | 2048 | 2082 |
| `SCA - lectura DI [2]` | input status | 2 | 0 | 0 / 14097 | 76 / 14173 | 4096 | 4172 |
| `SCA - comando DI [3]` | coil | 3 | 0 | 0 / 6145 | 42 / 6187 | 6144 | 6186 |

La lectura periódica recorre el `count` completo declarado por cada tabla. FC03 alcanza la fila 34 y FC01 la fila 42, incluidas las posiciones `y*`, para confirmar la imagen efectiva del PLC.

## Tablas SCA de producción

La UI muestra estas cuatro tablas como en el esquema SCA, en grilla 2x2 y con cantidad de tags exclusivamente de producción:

| Índice | Tabla | Tipo | FC lectura | Start ref | Start PDU | Count leído | Tags producción visibles |
|---:|---|---|---:|---:|---:|---:|---:|
| 0 | `SCA - lectura AN [0]` | input register | 04 | 30001 | 0 | 26 | 8 |
| 1 | `SCA - consigna AN [1]` | holding register | 03 | 42049 | 2048 | 35 | 17 |
| 2 | `SCA - lectura DI [2]` | input status | 02 | 14097 | 4096 | 77 | 42 |
| 3 | `SCA - comando DI [3]` | coil | 01 | 6145 | 6144 | 43 | 10 |

Las posiciones `y*` existen como área de escritura de inyección hacia el controlador y su lectura se usa solo como confirmación de sincronización. Para representar el proceso se siguen usando exclusivamente `e*`/`b*` del intercambio genuino.

Cada FC de lectura tiene habilitación y sample rate propios, persistidos en `runtime/modbus_polling.json`. El valor inicial es `enabled=true` y `sample_rate_ms=2000` para las cuatro. El planificador desfasa el comienzo de las consultas e independiza sus errores; las escrituras FC05/FC06 no dependen de estas llaves.

Las clases de valor del origen son `mval` (mapped value), `iprm` (integer parameter), `mbit` (mapped bit) y `bit`. Los registros son enteros de 16 bits con signo. Los niveles se expresan en milímetros, la turbiedad en miligramos de masa sólida por litro y las horas como contador entero directo. Toda variable booleana usa lógica positiva: `1` confirma lo que expresa el nombre.

## Zona de inyección

| Inyección | Entra por | Primera fila | Primera ref | Última fila | Última ref | Pisa |
|---|---|---:|---:|---:|---:|---|
| Lecturas analógicas | `SCA - consigna AN [1]` | 27 | 42076 | 34 | 42083 | `SCA - lectura AN [0]` |
| Lecturas digitales | `SCA - comando DI [3]` | 23 | 6168 | 42 | 6187 | `SCA - lectura DI [2]` |

## Tags de inyección analógica

| Fila entrada | Tag | Ref entrada | Pisa tag lectura |
|---:|---|---:|---|
| 27 | `yNvCamAsp` | 42076 | `eNvCamAsp` |
| 28 | `yNvRes` | 42077 | `eNvRes` |
| 29 | `yTurb` | 42078 | `eTurb` |
| 30 | `yB1Hs` | 42079 | `eB1Hs` |
| 31 | `yB2Hs` | 42080 | `eB2Hs` |
| 32 | `yB3Hs` | 42081 | `eB3Hs` |
| 33 | `yB4Hs` | 42082 | `eB4Hs` |
| 34 | `yB5Hs` | 42083 | `eB5Hs` |

## Tags de inyección digital

La primera señal es `yRFF` en fila 23/ref 6168 y la última es `yB5Falla` en fila 42/ref 6187. La memoria digital de inyección contiene `yRFF`, las peras de nivel de reserva/cámara y, por bomba, `RTU`, `EMar` y `Falla`. Las posiciones `yB#EMar` no aparecen en la tabla genérica de la UI ni se aceptan por su API: las gobierna exclusivamente el modo EMar del servidor.

| Grupo | Tags y filas |
|---|---|
| General y niveles | `yRFF` 23, `yResNvAtP` 24, `yResNvBjP` 25, `yCAspNvAtP` 26, `yCAspNvBjP` 27 |
| Bomba 1 | `yB1RTU` 28, `yB1EMar` 29, `yB1Falla` 30 |
| Bomba 2 | `yB2RTU` 31, `yB2EMar` 32, `yB2Falla` 33 |
| Bomba 3 | `yB3RTU` 34, `yB3EMar` 35, `yB3Falla` 36 |
| Bomba 4 | `yB4RTU` 37, `yB4EMar` 38, `yB4Falla` 39 |
| Bomba 5 | `yB5RTU` 40, `yB5EMar` 41, `yB5Falla` 42 |

## Comandos digitales de producción

Son bits mantenidos por el controlador. El cliente escribe una sola vez el `0` o `1` solicitado y usa FC01 para leer el estado conservado.

| Bomba | `cB#Aut` | `cB#Mr` |
|---:|---:|---:|
| 1 | 0 | 1 |
| 2 | 4 | 5 |
| 3 | 8 | 9 |
| 4 | 12 | 13 |
| 5 | 16 | 17 |


## Presentación web

Las tablas de producción se renderizan con columnas mínimas `fila`, `Name` y `Value`, respetando filas vacías internas hasta el último tag real de cada tabla. Las inyecciones `y*` se visualizan en dos tablas separadas: una para lecturas analógicas y otra para lecturas digitales.


## Actualización de lecturas digitales de bombas

Cada paquete de bomba incorpora `bB#Arndo` como último bit del grupo. Este indica positivamente que la bomba está arrancando y permite distinguirlo del feedback de marcha `bB#EMar`:

| Bomba | RTU | Aut | Ok | EMar | Falla | Arndo |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 26 | 27 | 28 | 29 | 31 | 32 |
| 2 | 37 | 38 | 39 | 40 | 42 | 43 |
| 3 | 48 | 49 | 50 | 51 | 53 | 54 |
| 4 | 59 | 60 | 61 | 62 | 64 | 65 |
| 5 | 70 | 71 | 72 | 73 | 75 | 76 |

El mapa conserva además la variable interna indicada por SCA en la columna `Value`. Para cada bomba la regla es `bB#RTU -> iB#RTU`, `bB#Aut -> B#Aut`, `bB#Ok -> B#Ok`, `bB#EMar -> iB#EMar`, `bB#Falla -> iB#Falla` y `bB#Arndo -> mB#Arr`.

Las restantes correspondencias son `eNvCamAsp -> iNvCamAsp`, `eNvRes -> iNvRes`, `eTurb -> iTurb`, `eB#Hs -> B#Hs`, `bRFF -> iRFF` (relé de falta de fase), `bResFR -> ResFR`, `bResRb -> ResRb`, `bResAt -> ResAt`, `bResBj -> ResBj`, `bResNvAtP -> ResNvAtP`, `bResNvBjP -> ResNvBjP`, `bCAspRb -> CAspRb`, `bCAspAt -> CAspAt`, `bCAspBj -> CAspBj`, `bCAspNvAtP -> CAspNvAtP` y `bCAspNvBjP -> CAspNvBjP`. Se exponen como `mapped_value` en la configuración/API y no reemplazan el valor vivo leído por Modbus.

`Sp` significa nivel superior y `Fn`, fondo. En reserva forman los límites de lectura sana; `bResFR` (fila 4, referencia `14101`, PDU `4100`) vale `1` únicamente cuando `eNvRes < gResFn` o `eNvRes > gResSp`. Los valores exactamente iguales a los límites se consideran sanos. Es una lectura calculada por el controlador y no existe un `yResFR` de inyección directa.
