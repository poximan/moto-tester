export type SignalScalar = boolean | number | string | null;
export type SignalQuality = "unknown" | "good" | "stale" | "error" | "local";
export type InjectionModeName = "disabled" | "enabled";
export type EmarMode = "disabled" | "automatic" | "forced";
export type EmulatorControlMode = "manual" | "automatic";

export interface ProjectDefinition {
  name: string;
  description: string;
}

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
  data_type: string | null;
  value_class: "mval" | "iprm" | "mbit" | "bit";
  positive_logic: boolean | null;
}

export interface TableDefinition {
  label: string;
  exchange_id: number;
  kind: string;
  value_class: "mval" | "iprm" | "mbit" | "bit";
  positive_logic: boolean | null;
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

export interface InjectionModeState {
  mode: InjectionModeName;
  enabled: boolean;
  path: string;
  error?: string | null;
}

export interface ConnectionState {
  connected: boolean;
  mode: "simulation" | "modbus";
  last_error: string | null;
}

export interface PumpSnapshot {
  id: number;
  emar_mode: EmarMode;
  rtu: SignalValue | null;
  aut: SignalValue | null;
  ok: SignalValue | null;
  running: SignalValue | null;
  arr: SignalValue | null;
  fault: SignalValue | null;
  hours: SignalValue | null;
  cmd_aut: SignalValue | null;
  cmd_mr: SignalValue | null;
}

export interface RuntimeSnapshot {
  project: ProjectDefinition;
  timestamp: number;
  connection: ConnectionState;
  injection_mode: InjectionModeState;
  modbus_polling: PollingState;
  controller: { host: string; port: number; unit_id: number };
  values: Record<string, SignalValue>;
  groups: { pumps: PumpSnapshot[] };
  events: Array<Record<string, unknown>>;
}

export interface TesterConfig {
  project: ProjectDefinition;
  controller: { host: string; port: number; unit_id: number; timeout_s: number };
  polling: { interval_ms: number; max_stale_ms: number };
  addressing_mode: string;
  injection_mode: InjectionModeState;
  modbus_polling: PollingState;
  field_emulator_url: string;
  tables: Record<string, TableDefinition>;
}

export interface EmulatorState {
  control_mode?: EmulatorControlMode;
  season_position_pct?: number;
  manual_inlet_open_pct?: number;
  manual_outlet_open_pct?: number;
  inlet_open_pct?: number;
  outlet_open_pct?: number;
  yNvCamAsp?: number;
  yNvRes?: number;
  pump_count?: number;
  injection_enabled?: boolean;
  last_error?: string;
  simulated_clock?: {
    day_index: number;
    day_key: string;
    hour: number;
    display_time: string;
  };
  rates?: {
    inlet_per_s: number;
    consumption_per_s: number;
    pump_per_s: number;
  };
  history?: {
    revision: number;
    sample_interval_s: number;
    retention_simulated_days: number;
    stored_points: number;
    file: string;
  };
  bounds?: {
    yNvCamAsp?: { floor: number; ceiling: number };
    yNvRes?: { floor: number; ceiling: number };
  };
}

export interface LevelHistoryPoint {
  timestamp_real: number;
  simulated_day_index: number;
  simulated_hour: number;
  chamber_level: number;
  reserve_level: number;
}

export interface LevelHistory {
  revision: number;
  sample_interval_s: number;
  retention_simulated_days: number;
  stored_points: number;
  file: string;
  points: LevelHistoryPoint[];
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
