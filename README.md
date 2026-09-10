# moto-tester

Emulador y observador del sistema de trasvase 4+1. El despliegue se define en
`docker-compose.yml` y usa `moto-tester-backend-net` para su red interna y
`servicoop-edge-net` como red externa de publicación.

## Componentes

| Componente | Responsabilidad | Puerto interno |
|---|---|---:|
| `trasvase-tester` | API, UI y cliente Modbus/TCP del PLC | `8080` |
| `field-emulator` | Modelo de niveles e inyección opcional | `8090` |

`trasvase-tester` es el único dueño de la conexión al PLC. `field-emulator` no
decide ni arranca bombas: lee estados confirmados y propone únicamente
`yNvCamAsp`/`yNvRes` cuando la inyección está habilitada.

## Configuración y estado

- `.env` contiene PLC, autenticación interna, polling, timeouts y parámetros del
  emulador; `.env.example` es la plantilla.
- `config/default.yaml` contiene exclusivamente el mapa Modbus y la estructura
  de las cuatro tablas SCA.
- `runtime/` es un volumen local: modos, controles de bombas, estado del
  emulador, histórico CSV y logs.
- `runtime/injection_mode.txt` habilita/deshabilita inyecciones genéricas `y*`.
- `runtime/pump_controls.json` conserva selectora Tablero/RTU y modo EMar.
- `runtime/modbus_polling.json` conserva el estado de FC01..FC04.

## Lecturas y escrituras

Las cuatro lecturas se planifican de forma independiente:

| Función | Rango | Uso |
|---|---:|---|
| FC04 | `30001..30026` | SCA lectura analógica |
| FC03 | `42049..42083` | consignas e inyección analógica |
| FC02 | `14097..14173` | SCA lectura digital y estados de bombas |
| FC01 | `6145..6187` | comandos e inyección digital |

Las consignas `g*`, comandos `c*` y `yB#EMar` se escriben por acción explícita.
Las inyecciones restantes `y*` requieren `injection_mode=enabled`. Los bits
`cB#Aut`/`cB#Mr` se escriben una sola vez por acción; el controlador mantiene su
estado. Toda señal booleana es de lógica positiva.

## Emulación de niveles

En automático, una hora real representa un día simulado. El consumo usa una curva
suave con valles y picos horarios; el ingreso a cámara usa una posición estacional
continua. El nivel de reserva recibe `12 mm/s` por bomba confirmada en marcha y
consume hasta `45,6 mm/s` al 100% (3,8 bombas), de modo que cuatro bombas superan
el pico por un margen del 5%. La quinta solo cuenta si el controlador confirma su
marcha. El emulador no selecciona bombas ni gobierna automatismos.

Niveles: milímetros. Turbiedad: miligramos de masa sólida por litro. Registros
analógicos: enteros con signo de 16 bits. `Sp` y `Fn` son límites de lectura sana;
`bResFR=1` confirma reserva fuera de ese rango.

## APIs

```text
GET  /api/health
GET  /api/snapshot
GET  /api/config
GET  /api/modbus-polling
PUT  /api/modbus-polling/{fc}
GET  /api/injection-mode
PUT  /api/injection-mode
GET  /api/emulator/state
GET  /api/emulator/history?max_points={n}
PUT  /api/emulator/control
PUT  /api/emulator/valves
POST /api/pumps/{id}/command
PUT  /api/pumps/{id}/emar-mode
POST /api/command
POST /api/injection
GET  /ws/stream
```

La UI usa WebSocket para snapshots continuos; REST queda para consulta y acciones
puntuales. Los clientes no leen archivos `runtime/`.

## Operación

```bash
docker compose up --build
```

La interfaz se publica mediante `edge-gateway` en:
`/moto-tester/`. No hay binding de puerto al host. El healthcheck del servicio web
coordina el arranque del emulador.

## Logs e histórico

```text
runtime/logs/trasvase-tester.log
runtime/logs/field-emulator.log
runtime/field_emulator_level_history.csv
```

Los endpoints `/api/logs`, `/api/diagnostics` y `/api/emulator/history` exponen
lectura controlada. El histórico conserva solo la ventana definida por la
configuración, sin base de datos adicional.

## Estructura

```text
config/default.yaml       mapa Modbus
trasvase-tester/app/      API, estado y cliente Modbus
trasvase-tester/frontend/ React/TypeScript
field-emulator/field_emulator/ modelo y persistencia CSV
tests/                    validaciones estáticas y de direccionamiento
```

## Contratos de escritura y reloj

Deshabilitar la inyección cancela las solicitudes pendientes de tags que requieren
ese modo. El permiso se comprueba nuevamente bajo el mismo bloqueo inmediatamente
antes de ejecutar Modbus. Una operación que ya estaba ejecutándose termina antes
de que se confirme la deshabilitación. Los comandos de marcha de bombas conservan
su permiso propio.

El emulador exige calidad `good` para límites, realimentaciones y estados de bombas,
y límites ordenados. Si falta una señal, no calcula ni escribe ese ciclo. Al salir
de inyección descarta el nivel simulado para resincronizarlo desde la realimentación.
No se crean límites de sustitución. La configuración numérica obligatoria se
valida al iniciar; un estado persistido ilegible o inválido no se reemplaza por defaults.

`moto_time` centraliza UTC, reloj monotónico y presentación UTC−3. Las duraciones,
el envejecimiento de señales y el muestreo usan el reloj monotónico. Las fechas de
muestras y la fase civil de la simulación conservan su timestamp UTC.

## Cambio de directorios persistentes (preparado, no ejecutado)

Antes de aplicar el nuevo Compose, detener ambos servicios y respaldar `runtime/`.
Copiar, sin borrar ni sobrescribir destinos existentes:

| Origen dentro de `runtime/` | Destino dentro de `runtime/` |
|---|---|
| `injection_mode.txt`, `modbus_polling.json`, `pump_controls.json` | `trasvase-tester/`, conservando nombres |
| `logs/trasvase-tester.log` y sus rotaciones | `trasvase-tester/logs/` |
| `field_emulator_state.json`, `field_emulator_level_history.csv` | `field-emulator/`, conservando nombres |
| `logs/field-emulator.log` y sus rotaciones | `field-emulator/logs/` |

Verificar contenido, propietario UID/GID 1000:1000 y permisos antes de iniciar.
Los volúmenes son independientes: el tester consulta el log remoto mediante
`GET /api/v1/logs` del emulador, expuesto al operador por `/api/logs/field-emulator`.
El endpoint devuelve hasta 300 líneas. No se comparte ningún directorio de datos.
Para volver al despliegue anterior, detener ambos servicios y restaurar juntos
el código/Compose y el respaldo anterior; no combinar estados de distintas fechas.
