# Trasvase Tester

Tester de frontera para sistema de control de bombas de trasvase 4+1.

La solución contiene tres componentes dockerizados:

1. **Servidor web**: dashboard para visualizar señales del intercambio, estado de bombas, comandos y dos tablas de inyección.
2. **Master Modbus/TCP**: cliente que consulta al PLC esclavo Modbus/TCP y, cuando se habilita explícitamente, escribe comandos/inyección. Corre dentro del servicio web en esta entrega.
3. **Servicio experto de emulación de campo**: contenedor separado que calcula y escribe `yNvCamAsp` y `yNvRes` a partir de válvulas regulables, niveles límite y bombas en marcha.

## Fuente de verdad de configuración

Hay una separación estricta:

- `.env`: **única fuente de verdad para configuración de despliegue**: PLC, puerto publicado en el host, polling, timeouts, modo simulación y parámetros del servicio experto.
- `runtime/write_mode.txt`: **única fuente de verdad del modo de escritura**, persistente y editable como texto. Se crea automáticamente en `read_only` si no existe. Valores válidos: `read_only` o `write_enabled`.
- `config/default.yaml`: **solo mapa Modbus y estructura de señales**: tablas, tags, filas, tipos y marcas de inyección.

El `docker-compose.yml` se limita a la orquestación: carga `.env`, publica `WEB_HOST_PORT`, conecta redes y monta `./runtime`. Los puertos internos `8080` y `8090`, los hosts de escucha, los comandos y el healthcheck pertenecen a sus Dockerfiles. La carpeta `runtime/` es local y generada; no forma parte de la imagen ni del repositorio. El código rechaza `server`, `controller`, `polling`, `safety` o `runtime` dentro de `config/default.yaml`.

## Etapa 1: observación

Modo equivalente a conectar un SCADA de lectura:

- Lee entradas analógicas reales `30001..30026` con FC04.
- Lee consignas analógicas reales `42049..42070` con FC03. La zona `y*` no se lee; solo se escribe para inyección y empieza en fila 27.
- Lee entradas digitales reales `14097..14177` con FC02. Incluye el nuevo bit `bB#Arr` en cada paquete de bomba.
- Lee comandos digitales reales `6145..6162` con FC01. La zona `y*` no se lee; solo se escribe para inyección y empieza en fila 23.
- La web permite generar comandos. Con `runtime/write_mode.txt = read_only` solo los registra localmente; con `write_enabled` se escriben al PLC. Las cuatro tablas SCA visibles muestran exclusivamente tags de producción, con filas internas vacías para respetar la distribución real. La zona `y*` no aparece en estas cuatro tablas; queda en las dos tablas de inyección. La actualización de estado en la web llega por WebSocket (`/ws/stream`) y se aplica incrementalmente sobre celdas ya existentes; no hay polling `fetch` periódico del snapshot ni reconstrucción de tablas durante el ciclo de actualización.

## Inyección

No hay tablas de fachada separadas. La UI separa la inyección en dos tablas: lecturas analógicas y lecturas digitales. La entrada Modbus queda dentro de las dos tablas escribibles/operativas:

| Tabla | Última fila real | Filas libres | Primera fila inyección | Primera ref inyección | Tags |
|---|---:|---:|---:|---:|---|
| `SCA - consigna AN [1]` | `21` | `22..26` | `27` | `42076` | `yNvCamAsp`, `yNvRes`, `yTurb`, `yB#Hs`; pisa `SCA - lectura AN [0]` |
| `SCA - comando DI [3]` | `17` | `18..22` | `23` | `6168` | `yRFF`, peras de reserva/cámara, y por bomba `RTU`, `EMar`, `Bypass`, `Falla`; pisa `SCA - lectura DI [2]` |

Las tablas de lecturas quedan exactamente como el intercambio informado:

| Tabla | Rango | Count |
|---|---:|---:|
| Lecturas analógicas | `30001..30026` | `26` |
| Lecturas digitales | `14097..14177` | `77` |

## Ejecución con Docker

Editar `.env` y luego ejecutar:

```bash
# desde la raíz del repositorio
docker compose up --build
```

Abrir la URL formada con `WEB_HOST_PORT` definido en `.env`, por defecto:

```text
http://localhost:8200
```

No hay scripts `run.sh` ni `run.bat`; la entrada operativa estándar es Docker Compose. En la raíz solo queda `docker-compose.yml` como archivo Docker; los Dockerfile están dentro de la carpeta del servicio que construyen: `trasvase-tester/Dockerfile` y `field-emulator/Dockerfile`.

## Desarrollo sin PLC

Cambiar `SIMULATION_MODE` en `.env` y levantar nuevamente el servicio.

## API principal

### Estado completo

REST sigue disponible para diagnóstico puntual:

```bash
curl http://localhost:<WEB_HOST_PORT>/api/snapshot
```

La UI usa WebSocket para tráfico continuo y no hace refresh periódico del snapshot:

```text
ws://localhost:<WEB_HOST_PORT>/ws/stream
```

### Salud

```bash
curl http://localhost:<WEB_HOST_PORT>/api/health
```

### Configuración y mapa calculado

```bash
curl http://localhost:<WEB_HOST_PORT>/api/config
```

### Modo de escritura persistente

```bash
curl http://localhost:<WEB_HOST_PORT>/api/write-mode
```

```bash
curl -X PUT http://localhost:<WEB_HOST_PORT>/api/write-mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"write_enabled","source":"operador"}'
```

Para volver al modo seguro:

```bash
curl -X PUT http://localhost:<WEB_HOST_PORT>/api/write-mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"read_only","source":"operador"}'
```


### Servicio experto de emulación

La web proxya el servicio experto por estos endpoints:

```bash
curl http://localhost:<WEB_HOST_PORT>/api/emulator/state
```

```bash
curl -X PUT http://localhost:<WEB_HOST_PORT>/api/emulator/valves \
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
curl -X POST http://localhost:<WEB_HOST_PORT>/api/pumps/1/command \
  -H "Content-Type: application/json" \
  -d '{"aut":true,"mr":true,"source":"web"}'
```

### Comando directo real por tag

```bash
curl -X POST http://localhost:<WEB_HOST_PORT>/api/command \
  -H "Content-Type: application/json" \
  -d '{"tag":"cB1Mr","value":true,"source":"curl"}'
```

### Inyección SCADA por tag `y*`

Requiere `runtime/write_mode.txt = write_enabled`. Con `read_only`, los pedidos se registran como locales y no se escriben al PLC. Las posiciones `y*` son solo entradas de inyección; para el estado visible del proceso se usan `eNvCamAsp`, `eNvRes` y el resto de `e*`/`b*`.

```bash
curl -X POST http://localhost:<WEB_HOST_PORT>/api/injection \
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
- `yB5Falla`: fila `47`, ref `6192`, PDU `6191`.

## Estructura del proyecto

```text
.env.example         Plantilla de parámetros runtime fijos.
docker-compose.yml   Orquestación de servicios; carga .env y monta runtime/ local.
runtime/             Estado local generado: write_mode.txt, logs y estado del emulador.
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

- Si `runtime/write_mode.txt` no existe, la aplicación lo crea en `read_only`.
- Hay una sola llave persistente de escritura: `runtime/write_mode.txt`.
- `read_only`: no escribe al PLC; refleja el pedido localmente para prueba de UI/API.
- `write_enabled`: permite escribir todos los tags marcados como `writable: true`, incluyendo `cB#*` y `y*`.
- El modo puede consultarse con `GET /api/write-mode` y cambiarse con `PUT /api/write-mode`; el cambio queda persistido en el archivo de texto.
- Las peticiones de comando se registran en eventos para trazabilidad.
- Los errores de lectura marcan calidad `error`; si la señal queda vieja, se marca `stale` en el snapshot.


## Generación asistida de EMar

En cada card de bomba existe un check `generar EMar`. Cuando está activo, el front escribe `yB#EMar` siguiendo el bit real `bB#Arr`: si `bB#Arr=1` escribe `yB#EMar=1`; si `bB#Arr=0` escribe `yB#EMar=0`. Si el check está desactivado, no toca `yB#EMar`.

La animación de bomba destella verde/azul cuando el arranque y la marcha no coinciden: `bB#Arr=1` con `bB#EMar=0`, o `bB#Arr=0` con `bB#EMar=1`. La jerarquía de colores se mantiene: sin conexión gris, falla roja, transición verde/azul, marcha verde, parada azul.


## Logs

Los logs persistentes se escriben en `runtime/logs/` y se pueden consultar desde la web en la sección **Diagnóstico y logs** o por API:

```bash
curl http://localhost:<WEB_HOST_PORT>/api/logs
curl "http://localhost:<WEB_HOST_PORT>/api/logs/trasvase-tester?lines=300"
curl "http://localhost:<WEB_HOST_PORT>/api/logs/field-emulator?lines=300"
curl http://localhost:<WEB_HOST_PORT>/api/diagnostics
```

Archivos principales:

- `runtime/logs/trasvase-tester.log`: servidor web, master Modbus integrado, lecturas, escrituras, errores de conexión y comandos.
- `runtime/logs/field-emulator.log`: servicio experto de emulación, válvulas y escrituras de `yNvCamAsp` / `yNvRes`.


## Acceso desde otra máquina de la LAN

El servidor web escucha dentro del contenedor en `WEB_HOST=0.0.0.0` y Docker publica el puerto explícitamente en todas las interfaces del host:

```yaml
ports:
  - "0.0.0.0:${WEB_HOST_PORT}:8080"
```

Para entrar desde otra máquina, usar la IP LAN del host donde corre Docker, no `localhost`:

```text
http://<IP_LAN_DEL_HOST_DOCKER>:8200
```

Chequeos rápidos en el host Docker:

```bash
docker compose ps
curl http://127.0.0.1:<WEB_HOST_PORT>/api/health
```

Verificar escucha del puerto:

```bash
ss -lntp | grep <WEB_HOST_PORT>
# o
netstat -ano | findstr :<WEB_HOST_PORT>
```

Si localmente responde pero desde otra PC no, el problema normalmente está fuera de la app: firewall del host, perfil de red privado/público en Windows, UFW/firewalld en Linux, Docker Desktop/WSL2 o segmentación/VLAN de la red.


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
curl http://127.0.0.1:<WEB_HOST_PORT>/api/health
```

El resultado `queued=True, written=False` en `/api/injection` solo significa que la escritura fue aceptada y encolada por el servicio web. La confirmación Modbus real aparece después en `runtime/logs/trasvase-tester.log` como `write_ok` o `write_error`.
