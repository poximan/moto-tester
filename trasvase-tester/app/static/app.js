const $ = (id) => document.getElementById(id);

let config = null;
let lastSnapshot = null;
let lastEmulator = null;
let viewsBuilt = false;
let valveSendTimer = null;
let draggingValve = null;
let streamSocket = null;
let streamReconnectTimer = null;
const inputDrafts = new Map();
const injectionStateOverrides = new Map();
const generateEmarEnabled = new Map();
const generatedEmarLastValue = new Map();

const scaTableOrder = ["analog_reads", "analog_setpoints", "digital_reads", "digital_commands"];
const pumpImages = {
  gray: "static/assets/pump_gray.png",
  red: "static/assets/pump_red.png",
  blue: "static/assets/pump_blue.png",
  green: "static/assets/pump_green.png",
};

function appPath(path) {
  return path.replace(/^\/+/, "");
}

function setText(el, text) {
  if (el && el.textContent !== String(text)) el.textContent = String(text);
}

function setPill(el, text, cls) {
  if (!el) return;
  setText(el, text);
  el.className = `pill ${cls || ""}`.trim();
  if (el.id === "write-pill") el.classList.add("mode-toggle");
}

function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(upper, value));
}

function qualityClass(q) {
  return `quality-${q || "unknown"}`;
}

function boolOn(signal) {
  if (!signal) return false;
  const value = Object.prototype.hasOwnProperty.call(signal, "value") ? signal.value : signal;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") return ["1", "true", "on", "si", "sí"].includes(value.toLowerCase());
  return false;
}

function valueText(signal) {
  if (!signal) return "--";
  const value = Object.prototype.hasOwnProperty.call(signal, "value") ? signal.value : signal;
  if (value === null || value === undefined) return "--";
  if (typeof value === "boolean") return value ? "1" : "0";
  return value;
}
function injectedValue(tag, fallback = null) {
  if (injectionStateOverrides.has(tag)) return injectionStateOverrides.get(tag);
  const signal = lastSnapshot?.values?.[tag];
  if (signal && Object.prototype.hasOwnProperty.call(signal, "value")) return signal.value;
  return fallback;
}

function injectedBool(tag, fallback = false) {
  return boolOn(injectedValue(tag, fallback));
}


function renderSignal(tag, snap) {
  const signal = snap.values[tag];
  const valueEl = $(tag);
  const metaEl = $(`${tag}-meta`);
  if (!valueEl || !metaEl) return;
  setText(valueEl, valueText(signal));
  setText(metaEl, signal
    ? `${signal.quality} · fila ${signal.row} · ref ${signal.reference} · ${signal.age_s ?? "--"} s`
    : "sin señal");
  metaEl.className = `meta ${qualityClass(signal?.quality)}`;
}

async function sendPump(pump, body) {
  const response = await fetch(appPath(`api/pumps/${pump}/command`), {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({...body, source: "web"})
  });
  if (!response.ok) {
    const error = await response.text();
    alert(`Error al enviar comando: ${error}`);
  }
}

async function setWriteMode(mode) {
  const response = await fetch(appPath("api/write-mode"), {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({mode, source: "web"})
  });
  if (!response.ok) {
    const error = await response.text();
    alert(`Error al cambiar modo de operación: ${error}`);
    return;
  }
  const payload = await response.json();
  if (lastSnapshot) {
    lastSnapshot.write_mode = {
      mode: payload.mode,
      write_enabled: payload.write_enabled,
      file: payload.file,
      error: payload.error,
    };
    renderSnapshot(lastSnapshot);
  }
}

async function toggleWriteMode() {
  const current = lastSnapshot?.write_mode?.mode || "read_only";
  const next = current === "write_enabled" ? "read_only" : "write_enabled";
  await setWriteMode(next);
}

function readInjectionDraft(tag) {
  const valueEl = $(`injection-input-${tag}`);
  if (!valueEl) return null;
  const value = valueEl.type === "checkbox" ? Boolean(valueEl.checked) : valueEl.value;
  inputDrafts.set(tag, value);
  return value;
}

async function sendInjection(tag) {
  const valueEl = $(`injection-input-${tag}`);
  if (!valueEl) return;
  const draft = readInjectionDraft(tag);
  let value;
  if (valueEl.type === "checkbox") {
    value = Boolean(draft);
  } else {
    value = Number(draft);
    if (Number.isNaN(value)) {
      alert(`Valor inválido para ${tag}`);
      return;
    }
  }
  const response = await fetch(appPath("api/injection"), {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({values: {[tag]: value}, source: "web"})
  });
  if (!response.ok) {
    const error = await response.text();
    alert(`Error al inyectar ${tag}: ${error}`);
    return;
  }
  injectionStateOverrides.set(tag, value);
  if (lastSnapshot?.values?.[tag]) {
    lastSnapshot.values[tag] = {...lastSnapshot.values[tag], value, quality: 'local'};
  }
  if (lastSnapshot) renderSnapshot(lastSnapshot);
}

async function sendRtuSelector(pump, isRtu) {
  const tag = `yB${pump}RTU`;
  const value = Boolean(isRtu);
  const response = await fetch(appPath("api/injection"), {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({values: {[tag]: value}, source: "web"})
  });
  if (!response.ok) {
    const error = await response.text();
    alert(`Error al escribir ${tag}: ${error}`);
    return;
  }
  injectionStateOverrides.set(tag, value);
  if (lastSnapshot?.values?.[tag]) {
    lastSnapshot.values[tag] = {...lastSnapshot.values[tag], value, quality: 'local'};
    renderSnapshot(lastSnapshot);
  }
}

function pumpVisualState(p, connected) {
  if (!connected) return {key: "gray", text: "sin conexión", blink: false};
  const ok = boolOn(p.ok);
  const running = boolOn(p.running);
  const arr = boolOn(p.arr);
  if (!ok) return {key: "red", text: "falla", blink: false};
  if (arr !== running) return {key: "blue", text: "transición arranque/marcha", blink: true};
  if (running) return {key: "green", text: "marcha", blink: false};
  return {key: "blue", text: "parada", blink: false};
}

function processPumpVisualState(p, connected) {
  // Vista resumida del proceso: solo azul, rojo y verde.
  // Sin conexión no usa gris; queda azul como estado neutro de sinóptico.
  if (connected && !boolOn(p.ok)) return {key: "red", text: "falla"};
  if (connected && boolOn(p.running)) return {key: "green", text: "marcha"};
  return {key: "blue", text: connected ? "parada" : "sin conexión"};
}

function updateProcessPumpBank(snap) {
  const pumps = snap.groups?.pumps || [];
  const connected = Boolean(snap.connection?.connected);
  pumps.forEach((p) => {
    const visual = processPumpVisualState(p, connected);
    const img = $(`process-pump-${p.id}`);
    if (!img) return;
    const next = pumpImages[visual.key];
    if (img.getAttribute("src") !== next) img.setAttribute("src", next);
    img.title = `Bomba ${p.id}: ${visual.text}`;
    img.alt = `Bomba ${p.id}: ${visual.text}`;
  });
}

function statusItemHtml(id, label, extraClass = "") {
  return `<div class="status-item ${extraClass}"><span>${label}</span><span id="${id}" class="dot"></span></div>`;
}

function emarEnabledInitial(pump) {
  return localStorage.getItem(`generate-emar-${pump}`) === "1";
}

function setGenerateEmar(pump, enabled) {
  generateEmarEnabled.set(pump, Boolean(enabled));
  localStorage.setItem(`generate-emar-${pump}`, enabled ? "1" : "0");
  if (!enabled) generatedEmarLastValue.delete(pump);
  if (lastSnapshot) processGenerateEmar(lastSnapshot);
}

async function writeGeneratedEmar(pump, value) {
  const tag = `yB${pump}EMar`;
  const response = await fetch(appPath("api/injection"), {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({values: {[tag]: Boolean(value)}, source: "web-generar-emar"})
  });
  if (!response.ok) {
    const error = await response.text();
    console.error(`Error al generar ${tag}`, error);
    generatedEmarLastValue.delete(pump);
    return;
  }
  injectionStateOverrides.set(tag, Boolean(value));
  generatedEmarLastValue.set(pump, Boolean(value));
  if (lastSnapshot?.values?.[tag]) {
    lastSnapshot.values[tag] = {...lastSnapshot.values[tag], value: Boolean(value), quality: "local"};
  }
}

function processGenerateEmar(snap) {
  const pumps = snap.groups?.pumps || [];
  pumps.forEach((p) => {
    const pump = p.id;
    if (!generateEmarEnabled.get(pump)) return;
    if (!p.arr || p.arr.value === null || p.arr.value === undefined) return;
    const arr = boolOn(p.arr);
    const last = generatedEmarLastValue.get(pump);
    if (last === arr) return;
    writeGeneratedEmar(pump, arr);
  });
}

function buildPumps() {
  const grid = $("pump-grid");
  if (!grid) return;
  grid.innerHTML = Array.from({length: 5}, (_, idx) => {
    const pump = idx + 1;
    return `
      <div class="pump" id="pump-${pump}">
        <div class="pump-head"><h3>Bomba ${pump}</h3></div>
        <div class="pump-top-row">
          <div class="selector-block" aria-label="Selectora RTU / Tablero">
            <div class="selector-legend"><span>RTU</span><span>Tablero</span></div>
            <button id="pump-${pump}-selector" class="two-pos-selector pos-rtu" type="button" title="RTU" aria-label="Selectora RTU / Tablero">
              <span class="selector-face"></span>
              <span class="selector-handle"></span>
            </button>
          </div>
          <div id="pump-visual-${pump}" class="pump-image-wrap state-gray">
            <img id="pump-img-${pump}" class="pump-image" alt="Estado bomba ${pump}" src="${pumpImages.gray}" />
            <img class="pump-image pump-image-green-overlay" alt="" src="${pumpImages.green}" />
          </div>
        </div>
        <div class="small">Horas: <strong id="pump-hours-${pump}">--</strong></div>
        <div class="status-list">
          <div class="status-row status-row-dual">
            ${statusItemHtml(`pump-${pump}-rtu`, "RTU")}
            ${statusItemHtml(`pump-${pump}-aut-state`, "Automatico")}
          </div>
          <div class="status-row status-row-health">
            ${statusItemHtml(`pump-${pump}-ok`, "Salud OK", "health-status")}
          </div>
          <div class="status-row status-row-emar">
            <label class="emar-generator">
              <input id="pump-${pump}-generate-emar" type="checkbox" />
              <span>generar EMar</span>
            </label>
            ${statusItemHtml(`pump-${pump}-running`, "EMar")}
          </div>
          <div class="status-row status-row-faults">
            ${statusItemHtml(`pump-${pump}-interlock`, "InE")}
            ${statusItemHtml(`pump-${pump}-fault`, "Falla")}
          </div>
        </div>
        <div class="pump-commands">
          <button id="pump-${pump}-aut-btn" class="toggle-btn aut-btn" type="button">Man</button>
          <button class="primary mr-on" type="button" onclick='sendPump(${pump}, {"mr": true})'>Marcha</button>
          <button class="danger mr-off" type="button" onclick='sendPump(${pump}, {"mr": false})'>Parada</button>
        </div>
      </div>`;
  }).join("");

  for (let pump = 1; pump <= 5; pump += 1) {
    const aut = $(`pump-${pump}-aut-btn`);
    if (aut) {
      aut.addEventListener("click", () => {
        const current = boolOn(lastSnapshot?.groups?.pumps?.[pump - 1]?.cmd_aut);
        sendPump(pump, {aut: !current});
      });
    }
    const selector = $(`pump-${pump}-selector`);
    if (selector) {
      selector.addEventListener("click", () => {
        const current = injectedBool(`yB${pump}RTU`, boolOn(lastSnapshot?.groups?.pumps?.[pump - 1]?.rtu));
        sendRtuSelector(pump, !current);
      });
    }
    const emar = $(`pump-${pump}-generate-emar`);
    const enabled = emarEnabledInitial(pump);
    generateEmarEnabled.set(pump, enabled);
    if (emar) {
      emar.checked = enabled;
      emar.addEventListener("change", () => setGenerateEmar(pump, emar.checked));
    }
  }
}

function setDot(id, signal) {
  const el = $(id);
  if (!el) return;
  const on = boolOn(signal);
  el.className = on ? "dot on" : "dot";
}

function setHealthDot(id, signal) {
  const el = $(id);
  if (!el) return;
  const ok = boolOn(signal);
  el.className = ok ? "dot on" : "dot bad";
}

function setFaultDot(id, signal) {
  const el = $(id);
  if (!el) return;
  const on = boolOn(signal);
  el.className = on ? "dot bad" : "dot";
}

function updatePumps(snap) {
  const pumps = snap.groups.pumps || [];
  const connected = Boolean(snap.connection?.connected);
  pumps.forEach((p) => {
    const visual = pumpVisualState(p, connected);
    const wrap = $(`pump-visual-${p.id}`);
    const img = $(`pump-img-${p.id}`);
    if (wrap) {
      wrap.className = `pump-image-wrap state-${visual.key} ${visual.blink ? "pump-transitioning" : ""}`.trim();
      wrap.setAttribute("title", visual.text);
    }
    if (img) {
      const baseKey = visual.blink ? "blue" : visual.key;
      const next = pumpImages[baseKey];
      if (img.getAttribute("src") !== next) img.setAttribute("src", next);
      img.setAttribute("title", visual.text);
      img.setAttribute("alt", `Bomba ${p.id}: ${visual.text}`);
    }
    setText($(`pump-hours-${p.id}`), valueText(p.hours));
    setDot(`pump-${p.id}-rtu`, p.rtu);
    const selector = $(`pump-${p.id}-selector`);
    if (selector) {
      const isRtu = injectedBool(`yB${p.id}RTU`, boolOn(p.rtu));
      selector.className = `two-pos-selector ${isRtu ? "pos-rtu" : "pos-tablero"}`;
      selector.title = isRtu ? "RTU" : "Tablero";
      selector.setAttribute("aria-label", `Selectora ${isRtu ? "RTU" : "Tablero"}`);
      selector.setAttribute("aria-pressed", isRtu ? "true" : "false");
    }
    setDot(`pump-${p.id}-aut-state`, p.aut);
    setHealthDot(`pump-${p.id}-ok`, p.ok);
    setDot(`pump-${p.id}-running`, p.running);
    setFaultDot(`pump-${p.id}-interlock`, p.interlock);
    setFaultDot(`pump-${p.id}-fault`, p.fault);
    const emar = $(`pump-${p.id}-generate-emar`);
    if (emar && emar.checked !== Boolean(generateEmarEnabled.get(p.id))) {
      emar.checked = Boolean(generateEmarEnabled.get(p.id));
    }

    const cmdAut = boolOn(p.cmd_aut);
    const autBtn = $(`pump-${p.id}-aut-btn`);
    if (autBtn) {
      setText(autBtn, cmdAut ? "Auto" : "Man");
      autBtn.className = `toggle-btn aut-btn ${cmdAut ? "on" : ""}`.trim();
    }
  });
}

function tableValueClass(signal) {
  return `value-cell ${qualityClass(signal?.quality)}`;
}

function tableVisibleMaxRow(table) {
  const production = (table.signals || []).filter(s => !s.facade);
  if (!production.length) return -1;
  return Math.max(...production.map(s => s.row));
}

function tableColumnLabel(tableName) {
  if (tableName === "analog_reads") return "Value (mval)";
  if (tableName === "analog_setpoints") return "Value (iprm)";
  if (tableName === "digital_reads") return "Value (mbit)";
  return "Value (bit)";
}

function productionSignals(table) {
  return (table.signals || []).filter(s => !s.facade);
}

function modbusTitleMeta(table) {
  const prod = productionSignals(table);
  const fc = prod[0]?.function_code || "--";
  const startRef = table.start_ref ?? prod[0]?.reference ?? "--";
  const startPdu = table.start_pdu ?? prod[0]?.pdu_address ?? "--";
  const lastProdRow = prod.length ? Math.max(...prod.map(s => s.row)) : "--";
  return `FC${fc} · inicio ${startRef} · offset ${startPdu} · prod 0..${lastProdRow}`;
}

function buildProductionTables() {
  const container = $("production-tables");
  if (!container || !config?.tables) return;
  container.innerHTML = scaTableOrder.map(tableName => {
    const table = config.tables[tableName];
    if (!table) return "";
    const prodSignals = productionSignals(table);
    const signalByRow = new Map(prodSignals.map(s => [s.row, s]));
    const maxRow = tableVisibleMaxRow(table);
    const rows = [];
    for (let row = 0; row <= maxRow; row += 1) {
      const sig = signalByRow.get(row);
      rows.push(`
        <tr class="${sig ? "" : "empty-row"}">
          <td class="addr">${row}</td>
          <td title="${sig ? `${sig.label || ""}${sig.mapped_value ? ` · variable interna ${sig.mapped_value}` : ""}` : ""}">${sig?.tag || ""}</td>
          <td id="prod-value-${sig?.tag || `${tableName}-${row}`}" class="value-cell quality-unknown" title=""></td>
        </tr>`);
    }
    const productionCount = prodSignals.length;
    const titleMeta = modbusTitleMeta(table);
    return `
      <article class="window-card sca-window ${tableName}">
        <div class="window-title">
          <span>${table.label}</span>
          <span class="window-modbus-meta">${titleMeta}</span>
          <small>${productionCount} tags producción</small>
        </div>
        <div class="table-scroll">
          <table class="sca-table">
            <thead><tr><th></th><th>Name</th><th>${tableColumnLabel(tableName)}</th></tr></thead>
            <tbody>${rows.join("")}</tbody>
          </table>
        </div>
      </article>`;
  }).join("");
}

function updateProductionTables(snap) {
  for (const tableName of scaTableOrder) {
    const table = config?.tables?.[tableName];
    if (!table) continue;
    for (const sig of (table.signals || []).filter(s => !s.facade)) {
      const signal = snap.values[sig.tag];
      const cell = $(`prod-value-${sig.tag}`);
      if (!cell) continue;
      setText(cell, valueText(signal));
      cell.className = tableValueClass(signal);
      cell.title = signal ? `ref ${signal.reference} · ${signal.quality || ""} ${signal.error || ""}` : "sin señal";
    }
  }
}

function injectionSignals(tableName) {
  return (config?.tables?.[tableName]?.signals || [])
    .filter(v => v.facade)
    .sort((a, b) => a.row - b.row);
}

function injectionInputHtml(v, tableName) {
  const saved = inputDrafts.get(v.tag);
  if (tableName === "digital_commands" || v.write_kind === "coil" || v.kind === "coil") {
    const checked = saved === true ? "checked" : "";
    return `<label class="checkcell"><input id="injection-input-${v.tag}" type="checkbox" ${checked} onchange='sendInjection("${v.tag}")' /> 1</label>`;
  }
  const value = saved === undefined ? "" : String(saved).replaceAll('"', '&quot;');
  return `<input id="injection-input-${v.tag}" class="value-input" type="number" step="1" value="${value}" oninput='readInjectionDraft("${v.tag}")' />`;
}

function targetTextFromConfig(v) {
  if (!v.injects_tag) return "--";
  const target = Object.values(config.tables)
    .flatMap(t => t.signals || [])
    .find(s => s.tag === v.injects_tag);
  if (!target) return v.injects_tag;
  return `${target.tag} · fila ${target.row}`;
}

function injectionEmptyRowHtml(row, isDigital) {
  return isDigital
    ? `<tr class="empty-row"><td class="addr">${row}</td><td></td><td></td><td></td><td></td></tr>`
    : `<tr class="empty-row"><td class="addr">${row}</td><td></td><td></td><td></td><td></td><td></td></tr>`;
}

function injectionRowHtml(v, tableName) {
  const isDigital = tableName === "digital_commands";
  const base = `
    <tr data-injection-tag="${v.tag}">
      <td class="addr">${v.row}</td>
      <td title="${v.label}">${v.tag}</td>
      <td>${targetTextFromConfig(v)}</td>
      <td id="injection-value-${v.tag}" class="value-cell quality-unknown"></td>
      <td>${injectionInputHtml(v, tableName)}</td>`;
  return isDigital ? `${base}</tr>` : `${base}<td><button type="button" onclick='sendInjection("${v.tag}")'>set</button></td></tr>`;
}

function buildInjectionTable(tableName, bodyId) {
  const body = $(bodyId);
  if (!body) return;
  const filter = ($("injection-filter")?.value || "").toLowerCase();
  const allRows = injectionSignals(tableName);
  const visibleRows = allRows.filter(v => !filter || `${v.tag} ${v.label} ${v.injects_tag || ""}`.toLowerCase().includes(filter));
  const isDigital = tableName === "digital_commands";

  if (!filter && allRows.length) {
    const byRow = new Map(allRows.map(v => [v.row, v]));
    const first = Math.max(0, allRows[0].row - 1);
    const last = allRows[allRows.length - 1].row;
    const rendered = [];
    for (let row = first; row <= last; row += 1) {
      const v = byRow.get(row);
      rendered.push(v ? injectionRowHtml(v, tableName) : injectionEmptyRowHtml(row, isDigital));
    }
    body.innerHTML = rendered.join("");
    return;
  }

  body.innerHTML = visibleRows.map(v => injectionRowHtml(v, tableName)).join("");
}

function buildInjections() {
  buildInjectionTable("analog_setpoints", "analog-injection-body");
  buildInjectionTable("digital_commands", "digital-injection-body");
  if (lastSnapshot) updateInjections(lastSnapshot);
}

function updateInjections(snap) {
  for (const tableName of ["analog_setpoints", "digital_commands"]) {
    for (const sig of injectionSignals(tableName)) {
      const raw = snap.values[sig.tag];
      const value = injectionStateOverrides.has(sig.tag)
        ? {...(raw || {}), value: injectionStateOverrides.get(sig.tag), quality: raw?.quality || "local"}
        : raw;
      const cell = $(`injection-value-${sig.tag}`);
      if (cell) {
        setText(cell, valueText(value));
        cell.className = tableValueClass(value);
        cell.title = value ? `ref ${value.reference || sig.reference} · ${value.quality || ""} ${value.error || ""}` : "sin señal";
      }
      const input = $(`injection-input-${sig.tag}`);
      if (input && document.activeElement !== input) {
        if (input.type === "checkbox") input.checked = boolOn(value);
        else if (value?.value !== undefined && value?.value !== null) input.value = value.value;
      }
    }
  }
}

function buildStaticViews() {
  if (viewsBuilt) return;
  buildPumps();
  buildProductionTables();
  buildInjections();
  wireValves();
  viewsBuilt = true;
}

async function fetchEmulator() {
  try {
    const response = await fetch(appPath("api/emulator/state"), {cache: "no-store"});
    if (!response.ok) throw new Error(await response.text());
    lastEmulator = await response.json();
  } catch (err) {
    lastEmulator = {last_error: String(err)};
  }
  renderEmulator();
}

function normalizeLevel(value, bounds) {
  if (value === null || value === undefined || !bounds) return null;
  const floor = Number(bounds.floor ?? 0);
  const ceiling = Number(bounds.ceiling ?? 1);
  const span = Math.max(Math.abs(ceiling - floor), 1);
  return clamp(((Number(value) - floor) / span) * 100, 0, 100);
}

function signalNumber(tag, fallback = null) {
  const signal = lastSnapshot?.values?.[tag];
  if (!signal || signal.value === null || signal.value === undefined) return fallback;
  const value = Number(signal.value);
  return Number.isFinite(value) ? value : fallback;
}

function processBounds() {
  return {
    yNvCamAsp: {
      floor: signalNumber("gCamFn", lastEmulator?.bounds?.yNvCamAsp?.floor ?? 0),
      ceiling: signalNumber("gCamRb", lastEmulator?.bounds?.yNvCamAsp?.ceiling ?? 4000),
    },
    yNvRes: {
      floor: signalNumber("gResFn", lastEmulator?.bounds?.yNvRes?.floor ?? -1),
      ceiling: signalNumber("gResSp", lastEmulator?.bounds?.yNvRes?.ceiling ?? 6000),
    },
  };
}

function setWaterHeight(selector, pct) {
  const el = document.querySelector(selector);
  if (!el || pct === null) return;
  el.style.height = `${clamp(pct, 3, 94)}%`;
}

function setValveVisual(which, pct) {
  const valve = $(which === "inlet" ? "inlet-valve" : "outlet-valve");
  const label = $(which === "inlet" ? "inlet-open-value" : "outlet-open-value");
  if (!valve) return;
  const safePct = clamp(Number(pct || 0), 0, 100);
  const angle = -75 + safePct * 1.5;
  valve.style.setProperty("--valve-angle", `${angle}deg`);
  const flap = valve.querySelector(".clapeta");
  if (flap) flap.style.transform = `rotate(${angle}deg)`;
  if (label) setText(label, `${Math.round(safePct)}%`);
}

function renderEmulator() {
  const emu = lastEmulator || {};
  const inletPct = Number(emu.inlet_open_pct || 0);
  const outletPct = Number(emu.outlet_open_pct || 0);
  setValveVisual("inlet", inletPct);
  setValveVisual("outlet", outletPct);

  // El dibujo muestra feedback de proceso, no el setpoint de inyección: el
  // agua visible depende de eNvCamAsp/eNvRes leídos desde el intercambio real.
  const bounds = processBounds();
  const camFeedback = signalNumber("eNvCamAsp", emu.yNvCamAsp ?? null);
  const resFeedback = signalNumber("eNvRes", emu.yNvRes ?? null);
  setText($("emu-yNvCamAsp"), camFeedback ?? "--");
  setText($("emu-yNvRes"), resFeedback ?? "--");

  setWaterHeight(".chamber-water", normalizeLevel(camFeedback, bounds.yNvCamAsp));
  setWaterHeight(".reserve-water", normalizeLevel(resFeedback, bounds.yNvRes));

  const meta = $("emulator-meta");
  if (meta) {
    const writeEnabled = emu.write_enabled;
    const camBounds = `Cam ${bounds.yNvCamAsp.floor}..${bounds.yNvCamAsp.ceiling}`;
    const resBounds = `Res ${bounds.yNvRes.floor}..${bounds.yNvRes.ceiling}`;
    const lastWrite = emu.last_write_values
      ? ` · yNvCamAsp=${emu.last_write_values.yNvCamAsp ?? "--"} · yNvRes=${emu.last_write_values.yNvRes ?? "--"}`
      : "";
    const modeText = writeEnabled === false ? "modo read_only" : "modo write_enabled";
    setText(meta, emu.last_error ? `error: ${emu.last_error}` : `${modeText} · ${camBounds} · ${resBounds} · bombas en marcha: ${emu.pump_count ?? "--"}${lastWrite}`);
    meta.className = `meta ${emu.last_error ? "quality-error" : (writeEnabled === false ? "quality-local" : "quality-good")}`;
  }
}

function scheduleValveWrite() {
  clearTimeout(valveSendTimer);
  valveSendTimer = setTimeout(sendValveOpenings, 180);
}

async function sendValveOpenings() {
  const inlet = Number(lastEmulator?.inlet_open_pct || 0);
  const outlet = Number(lastEmulator?.outlet_open_pct || 0);
  const response = await fetch(appPath("api/emulator/valves"), {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({inlet_open_pct: inlet, outlet_open_pct: outlet})
  });
  if (!response.ok) {
    const error = await response.text();
    alert(`Error al configurar válvulas: ${error}`);
    return;
  }
  lastEmulator = await response.json();
  renderEmulator();
}

function setValvePct(which, pct, persist = true) {
  const safePct = clamp(pct, 0, 100);
  lastEmulator = {
    ...(lastEmulator || {}),
    [which === "inlet" ? "inlet_open_pct" : "outlet_open_pct"]: safePct,
  };
  setValveVisual(which, safePct);
  if (persist) scheduleValveWrite();
}

function valvePctFromPointer(el, event) {
  const rect = el.getBoundingClientRect();
  return clamp(((event.clientX - rect.left) / Math.max(rect.width, 1)) * 100, 0, 100);
}

function wireValves() {
  for (const id of ["inlet-valve", "outlet-valve"]) {
    const valve = $(id);
    if (!valve) continue;
    const which = valve.dataset.which;
    valve.addEventListener("pointerdown", (event) => {
      draggingValve = {which, el: valve};
      valve.setPointerCapture(event.pointerId);
      setValvePct(which, valvePctFromPointer(valve, event));
    });
    valve.addEventListener("pointermove", (event) => {
      if (!draggingValve || draggingValve.el !== valve) return;
      setValvePct(which, valvePctFromPointer(valve, event));
    });
    valve.addEventListener("pointerup", () => {
      draggingValve = null;
      sendValveOpenings();
    });
    valve.addEventListener("dblclick", () => {
      const current = Number(lastEmulator?.[which === "inlet" ? "inlet_open_pct" : "outlet_open_pct"] || 0);
      setValvePct(which, current > 0 ? 0 : 100);
      sendValveOpenings();
    });
    valve.addEventListener("wheel", (event) => {
      event.preventDefault();
      const key = which === "inlet" ? "inlet_open_pct" : "outlet_open_pct";
      const current = Number(lastEmulator?.[key] || 0);
      setValvePct(which, current + (event.deltaY < 0 ? 5 : -5));
    }, {passive: false});
  }
}

async function loadDiagnostics() {
  const meta = $("logs-meta");
  const view = $("logs-view");
  try {
    const response = await fetch(appPath("api/diagnostics"), {cache: "no-store"});
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    if (meta) setText(meta, `diagnóstico · log_dir=${data.log_dir}`);
    if (view) view.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    if (meta) setText(meta, `error diagnóstico: ${err}`);
  }
}

async function loadLogsIndex() {
  const select = $("log-select");
  const meta = $("logs-meta");
  try {
    const response = await fetch(appPath("api/logs"), {cache: "no-store"});
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    if (select) {
      const current = select.value;
      select.innerHTML = data.files.map(f => `<option value="${f.name}">${f.filename} · ${f.size_bytes} bytes</option>`).join("");
      if (current && [...select.options].some(o => o.value === current)) select.value = current;
    }
    if (meta) setText(meta, `${data.files.length} log(s) · ${data.log_dir}`);
    if (data.files.length && !$("logs-view")?.dataset.loaded) {
      await loadSelectedLog();
    }
  } catch (err) {
    if (meta) setText(meta, `error listando logs: ${err}`);
  }
}

async function loadSelectedLog() {
  const select = $("log-select");
  const view = $("logs-view");
  const meta = $("logs-meta");
  const name = select?.value || "trasvase-tester";
  const lines = Number($("log-lines")?.value || 300);
  try {
    const response = await fetch(appPath(`api/logs/${encodeURIComponent(name)}?lines=${encodeURIComponent(lines)}`), {cache: "no-store"});
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    if (view) {
      view.dataset.loaded = "1";
      view.textContent = data.lines.length ? data.lines.join("\n") : `Sin líneas para ${data.filename}`;
      view.scrollTop = view.scrollHeight;
    }
    if (meta) setText(meta, `${data.filename} · ${data.exists ? data.lines.length + " líneas" : "no existe"}`);
  } catch (err) {
    if (meta) setText(meta, `error leyendo log: ${err}`);
  }
}


function renderSnapshot(snap) {
  lastSnapshot = snap;
  const conn = snap.connection || {};
  setPill($("conn-pill"), conn.connected ? "PLC: conectado" : "PLC: desconectado", conn.connected ? "pill-ok" : "pill-bad");
  const writeMode = snap.write_mode || {mode: "read_only", write_enabled: false};
  setPill($("write-pill"), writeMode.write_enabled ? "write_enabled" : "read_only", writeMode.write_enabled ? "pill-bad" : "pill-safe");
  const driverMode = conn.mode === "simulation" ? "Driver: simulación" : "Driver: Modbus/TCP";
  setPill($("mode-pill"), driverMode, conn.mode === "simulation" ? "pill-warn" : "");
  ["eNvCamAsp", "eNvRes", "eTurb"].forEach(tag => renderSignal(tag, snap));
  updatePumps(snap);
  updateProcessPumpBank(snap);
  processGenerateEmar(snap);
  updateProductionTables(snap);
  updateInjections(snap);
}

function streamUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const base = window.location.pathname.endsWith("/")
    ? window.location.pathname
    : `${window.location.pathname}/`;
  return `${proto}//${window.location.host}${base}ws/stream`;
}

function handleStreamMessage(payload) {
  if (payload.snapshot) renderSnapshot(payload.snapshot);
  if (payload.emulator) {
    lastEmulator = payload.emulator;
    renderEmulator();
  }
}

function connectStream() {
  clearTimeout(streamReconnectTimer);
  if (streamSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(streamSocket.readyState)) return;
  streamSocket = new WebSocket(streamUrl());
  streamSocket.addEventListener("open", () => {
    const mode = $("mode-pill");
    if (mode) mode.title = "WebSocket activo. El estado PLC se informa en la cápsula PLC.";
  });
  streamSocket.addEventListener("message", (event) => {
    try {
      handleStreamMessage(JSON.parse(event.data));
    } catch (err) {
      console.error("Mensaje websocket inválido", err);
    }
  });
  streamSocket.addEventListener("close", () => {
    setPill($("conn-pill"), "WEB: reconectando", "pill-warn");
    streamReconnectTimer = setTimeout(connectStream, 1500);
  });
  streamSocket.addEventListener("error", () => {
    try { streamSocket.close(); } catch (_) { /* noop */ }
  });
}

async function loadConfig() {
  const response = await fetch(appPath("api/config"), {cache: "no-store"});
  config = await response.json();
}

function wireFilters() {
  const injectionFilter = $("injection-filter");
  if (injectionFilter) injectionFilter.addEventListener("input", () => buildInjections());
}

wireFilters();
loadConfig().then(() => {
  buildStaticViews();
  loadLogsIndex();
  connectStream();
}).catch((err) => {
  setPill($("conn-pill"), "config error", "pill-bad");
  console.error(err);
});
