export type SignalScalar = boolean | number | string | null;
export type SignalQuality = "unknown" | "good" | "stale" | "error" | "local";
export type WriteModeName = "read_only" | "write_enabled";

export interface SignalValue {
  tag: string;
  label: string;
  mapped_value: string | null;
  table: string;
  kind: string;
  row: number;
  reference: number;
  pdu_address: number;
  function_code: string;
  writable: boolean;
  facade: boolean;
  value: SignalScalar;
  quality: SignalQuality;
  age_s: number | null;
  error: string | null;
}

export interface SignalDefinition {
  row: number;
  tag: string;
  label: string;
  mapped_value: string | null;
  reference: number;
  pdu_address: number;
  function_code: string;
  writable: boolean;
  facade: boolean;
  write_kind: string | null;
  injects_tag: string | null;
  data_type: string;
}

export interface TableDefinition {
  label: string;
  kind: string;
  start_ref: number;
  start_pdu: number;
  count: number;
  writable: boolean;
  signals: SignalDefinition[];
}

export interface PollingFunction {
  function_code: string;
  enabled: boolean;
  sample_rate_ms: number;
  last_error: string | null;
}

export interface PollingState {
  revision: number;
  functions: Record<string, PollingFunction>;
}

export interface WriteModeState {
  mode: WriteModeName;
  write_enabled: boolean;
  file?: string;
  error?: string | null;
}

export interface ConnectionState {
  connected: boolean;
  mode: "simulation" | "modbus";
  last_error: string | null;
}

export interface PumpSnapshot {
  id: number;
  rtu: SignalValue | null;
  aut: SignalValue | null;
  ok: SignalValue | null;
  running: SignalValue | null;
  arr: SignalValue | null;
  interlock: SignalValue | null;
  fault: SignalValue | null;
  hours: SignalValue | null;
  cmd_aut: SignalValue | null;
  cmd_mr: SignalValue | null;
}

export interface RuntimeSnapshot {
  project: string;
  timestamp: number;
  connection: ConnectionState;
  write_mode: WriteModeState;
  modbus_polling: PollingState;
  controller: { host: string; port: number; unit_id: number };
  values: Record<string, SignalValue>;
  groups: { pumps: PumpSnapshot[] };
  events: Array<Record<string, unknown>>;
}

export interface TesterConfig {
  project: string;
  controller: { host: string; port: number; unit_id: number; timeout_s: number };
  polling: { interval_ms: number; max_stale_ms: number };
  addressing_mode: string;
  write_mode: WriteModeState;
  modbus_polling: PollingState;
  field_emulator_url: string;
  tables: Record<string, TableDefinition>;
}

export interface EmulatorState {
  inlet_open_pct?: number;
  outlet_open_pct?: number;
  yNvCamAsp?: number;
  yNvRes?: number;
  pump_count?: number;
  write_enabled?: boolean;
  last_error?: string;
  bounds?: {
    yNvCamAsp?: { floor: number; ceiling: number };
    yNvRes?: { floor: number; ceiling: number };
  };
}

export interface StreamPayload {
  type: "state";
  snapshot: RuntimeSnapshot;
  emulator: EmulatorState;
}

export interface LogFile {
  name: string;
  filename: string;
  size_bytes: number;
}

export interface LogIndex {
  log_dir: string;
  files: LogFile[];
}

export interface LogContent {
  name: string;
  filename: string;
  exists: boolean;
  lines: string[];
}
