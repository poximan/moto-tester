# Mapa Modbus

Modo de direccionamiento: `modicon_reference`. Las referencias verificadas se calculan con la fórmula ACE3600 `offset + Z*2048 + X*256 + Y`; en este intercambio se usa `X=0`. Luego se convierten internamente a PDU cero-based.


## Fórmula ACE3600 validada

| Tabla | Kind | Z | X | Primera fila/ref | Última fila/ref | PDU primera | PDU última |
|---|---|---:|---:|---:|---:|---:|---:|
| `SCA - lectura AN [0]` | input register | 0 | 0 | 0 / 30001 | 25 / 30026 | 0 | 25 |
| `SCA - consigna AN [1]` | holding register | 1 | 0 | 0 / 42049 | 34 / 42083 | 2048 | 2082 |
| `SCA - lectura DI [2]` | input status | 2 | 0 | 0 / 14097 | 80 / 14177 | 4096 | 4176 |
| `SCA - comando DI [3]` | coil | 3 | 0 | 0 / 6145 | 47 / 6192 | 6144 | 6191 |

La lectura periódica corta en el último tag de producción de las tablas escribibles: fila 21 para consignas analógicas y fila 17 para comandos digitales. Las filas `y*` no se leen como feedback.

## Tablas SCA de producción

La UI muestra estas cuatro tablas como en el esquema SCA, en grilla 2x2 y con cantidad de tags exclusivamente de producción:

| Índice | Tabla | Tipo | FC lectura | Start ref | Start PDU | Count leído | Tags producción visibles |
|---:|---|---|---:|---:|---:|---:|---:|
| 0 | `SCA - lectura AN [0]` | input register | 04 | 30001 | 0 | 26 | 8 |
| 1 | `SCA - consigna AN [1]` | holding register | 03 | 42049 | 2048 | 22 | 17 |
| 2 | `SCA - lectura DI [2]` | input status | 02 | 14097 | 4096 | 81 | 51 |
| 3 | `SCA - comando DI [3]` | coil | 01 | 6145 | 6144 | 18 | 10 |

La lectura periódica de producción no incluye la zona `y*`. Esas posiciones existen solo como área de escritura de inyección hacia el controlador. Para representar proceso se leen únicamente `e*`/`b*` del intercambio genuino.

## Zona de inyección

| Inyección | Entra por | Primera fila | Primera ref | Última fila | Última ref | Pisa |
|---|---|---:|---:|---:|---:|---|
| Lecturas analógicas | `SCA - consigna AN [1]` | 27 | 42076 | 34 | 42083 | `SCA - lectura AN [0]` |
| Lecturas digitales | `SCA - comando DI [3]` | 23 | 6168 | 47 | 6192 | `SCA - lectura DI [2]` |

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

La primera señal es `yRFF` en fila 23/ref 6168 y la última es `yB5Falla` en fila 47/ref 6192. La tabla digital de inyección ahora contiene solo `yRFF`, peras de nivel de reserva/cámara, y por bomba `RTU`, `EMar`, `Bypass` y `Falla`.


## Presentación web

Las tablas de producción se renderizan con columnas mínimas `fila`, `Name` y `Value`, respetando filas vacías internas hasta el último tag real de cada tabla. Las inyecciones `y*` se visualizan en dos tablas separadas: una para lecturas analógicas y otra para lecturas digitales.


## Actualización de lecturas digitales de bombas

Cada paquete de bomba incorpora `bB#Arr` como último bit del grupo. Ese bit permite distinguir orden/arranque respecto del feedback de marcha `bB#EMar`:

| Bomba | RTU | Aut | Ok | EMar | Bypass | InE | Falla | Arr |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 26 | 27 | 28 | 29 | 30 | 31 | 32 | 33 |
| 2 | 38 | 39 | 40 | 41 | 42 | 43 | 44 | 45 |
| 3 | 50 | 51 | 52 | 53 | 54 | 55 | 56 | 57 |
| 4 | 61 | 62 | 63 | 64 | 65 | 66 | 67 | 68 |
| 5 | 73 | 74 | 75 | 76 | 77 | 78 | 79 | 80 |
