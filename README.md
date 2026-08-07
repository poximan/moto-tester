# Trasvase Tester

Tester de frontera para sistema de control de bombas de trasvase 4+1.

La solución contiene tres componentes dockerizados:

1. **Servidor web**: dashboard para visualizar señales del intercambio, estado de bombas, comandos y dos tablas de inyección.
2. **Master Modbus/TCP**: cliente que consulta al PLC esclavo Modbus/TCP y, cuando se habilita explícitamente, escribe comandos/inyección. Corre dentro del servicio web en esta entrega.
3. **Servicio experto de emulación de campo**: contenedor separado que calcula y escribe `yNvCamAsp` y `yNvRes` a partir de válvulas regulables, niveles límite y bombas en marcha.

## Fuente de verdad de configuración

Hay una separación estricta:

- `.env`: **única fuente de verdad para configuración de despliegue**: PLC, autenticación interna, interlock, polling, timeouts, modo simulación y parámetros del servicio experto.
- `runtime/write_mode.txt`: estado efectivo del modo de escritura. Cada arranque lo fuerza a `read_only`; `write_enabled` sólo se admite con interlock local armado y lease vigente.
- `runtime/modbus_polling.json`: control persistente e independiente de las lecturas FC01, FC02, FC03 y FC04. Todas nacen activas usando `POLL_INTERVAL_MS` —2000 ms en el `.env.example`—; la botonera de cabecera permite pausar cada una o cambiar su período sin afectar las escrituras FC05/FC06.
- `config/default.yaml`: **solo mapa Modbus y estructura de señales**: tablas, tags, filas, tipos, marcas de inyección y, cuando SCA la informa, variable interna `mapped_value`.

El `docker-compose.yml` se limita a la orquestación: carga `.env`, conecta redes y monta `./runtime`. El servicio web no publica puertos del host y sólo se alcanza mediante `edge-gateway`. Los puertos internos `8080` y `8090`, los hosts de escucha, los comandos y el healthcheck pertenecen a sus Dockerfiles. La carpeta `runtime/` es local y generada; no forma parte de la imagen ni del repositorio. El código rechaza `server`, `controller`, `polling`, `safety` o `runtime` dentro de `config/default.yaml`.

## Etapa 1: observación

Modo equivalente a conectar un SCADA de lectura:

- Lee entradas analógicas reales `30001..30026` con FC04.
- Lee consignas analógicas reales `42049..42070` con FC03. La zona `y*` no se lee; solo se escribe para inyección y empieza en fila 27.
- Lee entradas digitales reales `14097..14173` con FC02. Conserva `bB#InE` e incluye `bB#Arndo` al final de cada paquete de bomba.
- Lee comandos digitales reales `6145..6162` con FC01. La zona `y*` no se lee; solo se escribe para inyección y empieza en fila 23.
- Las cuatro lecturas se planifican por separado y con inicio desfasado para no concentrar una ráfaga sobre el controlador. Un error de una FC queda aislado y no descarta las lecturas correctas de las demás.
- La web permite generar comandos. Con `runtime/write_mode.txt = read_only` solo los registra localmente; con `write_enabled` se escriben al PLC. Las cuatro tablas SCA visibles muestran exclusivamente tags de producción, con filas internas vacías para respetar la distribución real. La zona `y*` no aparece en estas cuatro tablas; queda en las dos tablas de inyección. La actualización de estado en la web llega por WebSocket (`/ws/stream`) y se aplica incrementalmente sobre celdas ya existentes; no hay polling `fetch` periódico del snapshot ni reconstrucción de tablas durante el ciclo de actualización.

La cápsula `Fuente` de la cabecera solo informa de dónde salen los valores mostrados: PLC real con host e ID Modbus, o simulador local. No habilita tráfico ni cambia el modo de escritura.

## Inyección

No hay tablas de fachada separadas. La UI separa la inyección en dos tablas: lecturas analógicas y lecturas digitales. La entrada Modbus queda dentro de las dos tablas escribibles/operativas:

| Tabla | Última fila real | Filas libres | Primera fila inyección | Primera ref inyección | Tags |
|---|---:|---:|---:|---:|---|
| `SCA - consigna AN [1]` | `21` | `22..26` | `27` | `42076` | `yNvCamAsp`, `yNvRes`, `yTurb`, `yB#Hs`; pisa `SCA - lectura AN [0]` |
| `SCA - comando DI [3]` | `17` | `18..22` | `23` | `6168` | `yRFF`, peras de reserva/cámara, y por bomba `RTU`, `EMar`, `Falla`; pisa `SCA - lectura DI [2]` |

Las tablas de lecturas quedan exactamente como el intercambio informado:

| Tabla | Rango | Count |
|---|---:|---:|
| Lecturas analógicas | `30001..30026` | `26` |
| Lecturas digitales | `14097..14173` | `77` |

## Ejecución con Docker

Editar `.env` y luego ejecutar:

```bash
# desde la raíz del repositorio
docker compose up --build
```

Abrir la URL pública del gateway e iniciar el modo protegido:

```text
https://comunicaciones.servicoop.com.ar/moto-tester/
```

No hay scripts `run.sh` ni `run.bat`; la entrada operativa estándar es Docker Compose. En la raíz solo queda `docker-compose.yml` como archivo Docker; los Dockerfile están dentro de la carpeta del servicio que construyen: `trasvase-tester/Dockerfile` y `field-emulator/Dockerfile`.

## Desarrollo sin PLC

Cambiar `SIMULATION_MODE` en `.env` y levantar nuevamente el servicio.

## API principal

### Estado completo

REST sigue disponible para diagnóstico puntual:

```bash
curl https://comunicaciones.servicoop.com.ar/moto-tester/api/snapshot
```

La UI usa WebSocket para tráfico continuo y no hace refresh periódico del snapshot:

```text
wss://comunicaciones.servicoop.com.ar/moto-tester/ws/stream
```

### Salud

```bash
curl https://comunicaciones.servicoop.com.ar/moto-tester/api/health
```

### Configuración y mapa calculado

```bash
curl https://comunicaciones.servicoop.com.ar/moto-tester/api/config
```

### Control de lecturas Modbus

La cabecera expone una tecla por función de lectura. El estado y el sample rate se guardan en `runtime/modbus_polling.json`, por lo que sobreviven a la recreación de contenedores mientras se conserve el volumen `runtime/`:

```bash
curl https://comunicaciones.servicoop.com.ar/moto-tester/api/modbus-polling
curl -X PUT https://comunicaciones.servicoop.com.ar/moto-tester/api/modbus-polling/02 \
  -H "Content-Type: application/json" \
  -d '{"enabled":false,"sample_rate_ms":2000,"source":"operador"}'
```

FC01..FC04 gobiernan exclusivamente lecturas. Las escrituras de coils FC05 y registros FC06 continúan dependiendo de `runtime/write_mode.txt`.

### Modo de escritura temporal con interlock

Antes de habilitar escritura, un operador con acceso al volumen local debe escribir exactamente `armed` en `runtime/write_interlock.txt`. La API requiere la sesión protegida del gateway y la habilitación vence luego de `WRITE_ENABLE_LEASE_SECONDS` (900 segundos en el ejemplo).

```bash
curl https://comunicaciones.servicoop.com.ar/moto-tester/api/write-mode
```

```bash
curl -X PUT https://comunicaciones.servicoop.com.ar/moto-tester/api/write-mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"write_enabled","source":"operador"}'
```

Para volver al modo seguro:

```bash
curl -X PUT https://comunicaciones.servicoop.com.ar/moto-tester/api/write-mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"read_only","source":"operador"}'
```


### Servicio experto de emulación

La web proxya el servicio experto por estos endpoints:

```bash
curl https://comunicaciones.servicoop.com.ar/moto-tester/api/emulator/state
```

```bash
curl -X PUT https://comunicaciones.servicoop.com.ar/moto-tester/api/emulator/valves \
  -H "Content-Type: application/json" \
  -d '{"inlet_open_pct":60,"outlet_open_pct":25}'
```

El servicio experto no tiene una llave propia de habilitación: calcula siempre, pero solo escribe efectivamente cuando el modo superior está en `write_enabled`. Modelo inicial implementado:

- `yNvCamAsp` se incrementa por la válvula de ingreso y se decrementa por bombas en marcha.
- `yNvRes` se incrementa por bombas en marcha y se decrementa por la válvula de salida. La escala por defecto de salida es proporcional: con 3 bombas en marcha y la válvula de reserva al 50%, el caudal de salida empata el caudal que entra a reserva. Con menos bombas o menor apertura la reserva sube; con más bombas o mayor apertura baja según la diferencia neta.
- `yNvRes` queda acotado por `gResFn..gResSp`.
- `yNvCamAsp` queda acotado por `gCamFn..gCamRb`.

### Comando de bomba

En etapa 1 queda local y no escribe al PLC mientras `runtime/write_mode.txt` esté en `read_only`:

```bash
curl -X POST https://comunicaciones.servicoop.com.ar/moto-tester/api/pumps/1/command \
  -H "Content-Type: application/json" \
  -d '{"aut":true,"mr":true,"source":"web"}'
```

### Comando directo real por tag

```bash
curl -X POST https://comunicaciones.servicoop.com.ar/moto-tester/api/command \
  -H "Content-Type: application/json" \
  -d '{"tag":"cB1Mr","value":true,"source":"curl"}'
```

### Inyección SCADA por tag `y*`

Requiere `runtime/write_mode.txt = write_enabled`. Con `read_only`, los pedidos se registran como locales y no se escriben al PLC. Las posiciones `y*` son solo entradas de inyección; para el estado visible del proceso se usan `eNvCamAsp`, `eNvRes` y el resto de `e*`/`b*`.

```bash
curl -X POST https://comunicaciones.servicoop.com.ar/moto-tester/api/injection \
  -H "Content-Type: application/json" \
  -d '{"values":{"yNvCamAsp":2500,"yB1EMar":true},"source":"scada-test"}'
```

## Direccionamiento Modbus

El mapa usa la fórmula ACE3600 `offset + Z*2048 + X*256 + Y`, con `X=0` para estas cuatro tablas SCA. La columna `Value` que aparece en la documentación es semántica del tag/mapped value, no una columna Modbus adicional a leer. Con `addressing.mode: modicon_reference`, las referencias documentadas se convierten a direcciones PDU cero-based para `pymodbus`:

- `30001` -> `0`
- `42049` -> `2048`
- `14097` -> `4096`
- `6145` -> `6144`

Direcciones relevantes de inyección:

- `yNvCamAsp`: fila `27`, ref `42076`, PDU `2075`.
- `yB5Hs`: fila `34`, ref `42083`, PDU `2082`.
- `yRFF`: fila `23`, ref `6168`, PDU `6167`.
- `yB5Falla`: fila `42`, ref `6187`, PDU `6186`.

## Estructura del proyecto

```text
.env.example         Plantilla de parámetros runtime fijos.
docker-compose.yml   Orquestación de servicios; carga .env y monta runtime/ local.
runtime/             Estado local generado: write_mode.txt, modbus_polling.json, logs y estado del emulador.
trasvase-tester/
  Dockerfile         Imagen del servicio web + master Modbus.
  app/               Paquete Python importable del servicio.
    main.py          FastAPI + endpoints.
    modbus_client.py Poller Modbus/TCP y modo simulación.
    config.py        Carga de .env + mapa Modbus; valida separación de responsabilidades.
    addressing.py    Conversión Modicon <-> PDU.
    state.py         Estado runtime, snapshots, cola de escritura.
    write_mode.py    Lectura/escritura persistente de runtime/write_mode.txt.
    static/          UI web: tablas SCA, bombas, válvulas e inyecciones separadas.
      assets/        PNGs de bombas por estado.
field-emulator/
  Dockerfile         Imagen del servicio experto.
  requirements.txt   Dependencias del servicio experto.
  field_emulator/    Paquete Python importable del servicio.
    main.py          Modelo de niveles + escritura yNvCamAsp/yNvRes.
config/
  default.yaml       Solo mapa Modbus y señales.
docs/
  MAPA_MODBUS.md     Mapa de intercambio e inyección.
  FRONTERA.md        Criterios de frontera y etapa 2.
tests/
  test_addressing.py
  test_config.py
```

## Seguridad operativa

- El contenedor siempre inicia en `read_only`, incluso si el archivo persistido tenía otro valor.
- Para habilitar escritura deben coincidir tres controles: sesión protegida válida, `runtime/write_interlock.txt = armed` y lease vigente.
- El lease vence automáticamente y cualquier interlock ausente, inválido o desarmado produce cierre en `read_only`.
- Las llamadas internas del `field-emulator` usan un token propio; no pueden habilitar el modo de escritura ni modificar otros controles.
- Los lotes se validan completos —tags, permisos, tipos, rangos y capacidad— antes de encolar, evitando escrituras parciales.
- Las peticiones de comando se registran en eventos para trazabilidad.
- Los errores de lectura marcan calidad `error`; si la señal queda vieja, se marca `stale` en el snapshot.


## Generación asistida de EMar

En cada card de bomba existe un check `generar EMar`. Cuando está activo, el front escribe `yB#EMar` siguiendo el bit real `bB#Arndo`: si `bB#Arndo=1` escribe `yB#EMar=1`; si `bB#Arndo=0` escribe `yB#EMar=0`. Si el check está desactivado, no toca `yB#EMar`.

La animación de bomba destella verde/azul cuando el arranque y la marcha no coinciden: `bB#Arndo=1` con `bB#EMar=0`, o `bB#Arndo=0` con `bB#EMar=1`. La jerarquía de colores se mantiene: sin conexión gris, falla roja, transición verde/azul, marcha verde, parada azul.


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


## Acceso

`trasvase-tester` sólo expone el puerto interno `8080` en `servicoop-edge-net`. No existe binding al host ni acceso LAN directo. Todo acceso de operador entra por `https://comunicaciones.servicoop.com.ar/moto-tester/`, donde `edge-gateway` valida la sesión protegida. Los endpoints mutables vuelven a verificar esa sesión en el servicio.
## Orden de arranque y error `Connection refused` del emulador

El `field-emulator` consume la API interna del servicio web en `http://trasvase-tester:8080`. Si el emulador arranca antes de que Uvicorn esté aceptando conexiones, aparece un error transitorio:

```text
<urlopen error [Errno 111] Connection refused>
```

Esto no indica un problema Modbus; significa que la API web todavía no estaba lista. El Dockerfile de `trasvase-tester` define el `healthcheck` sobre `/api/health`; Compose solamente hace que `field-emulator` espere a que el servicio esté `healthy`. Además, el emulador registra ese caso como warning resumido, no como stack trace repetitivo.

Si vuelve a aparecer, revisar:

```bash
docker compose ps
docker logs trasvase-tester --tail=100
docker logs field-emulator --tail=100
docker compose exec trasvase-tester python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2)"
```

El resultado `queued=True, written=False` en `/api/injection` solo significa que la escritura fue aceptada y encolada por el servicio web. La confirmación Modbus real aparece después en `runtime/logs/trasvase-tester.log` como `write_ok` o `write_error`.
