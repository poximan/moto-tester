import type {
  EmulatorState,
  LogContent,
  LogIndex,
  RuntimeSnapshot,
  StreamPayload,
  TesterConfig,
} from "./TrasvaseModels";

export class TrasvaseContractParser {
  public parseConfig(payload: unknown): TesterConfig {
    const record = this.requireRecord(payload, "config");
    this.requireProject(record.project, "config.project");
    this.requireRecord(record.controller, "config.controller");
    this.requireRecord(record.polling, "config.polling");
    this.requireRecord(record.injection_mode, "config.injection_mode");
    this.requirePolling(record.modbus_polling, "config.modbus_polling");
    const tables = this.requireRecord(record.tables, "config.tables");
    for (const [name, value] of Object.entries(tables)) {
      const table = this.requireRecord(value, `config.tables.${name}`);
      if (!Array.isArray(table.signals)) {
        throw new Error(`Contrato inválido: config.tables.${name}.signals debe ser una lista`);
      }
      table.signals.forEach((signal, index) => {
        const entry = this.requireRecord(signal, `config.tables.${name}.signals[${index}]`);
        this.requireString(entry, "tag", `config.tables.${name}.signals[${index}]`);
        this.requireNumber(entry, "row", `config.tables.${name}.signals[${index}]`);
      });
    }
    return record as unknown as TesterConfig;
  }

  public parseSnapshot(payload: unknown): RuntimeSnapshot {
    const record = this.requireRecord(payload, "snapshot");
    this.requireProject(record.project, "snapshot.project");
    this.requireNumber(record, "timestamp", "snapshot");
    this.requireRecord(record.connection, "snapshot.connection");
    this.requireRecord(record.injection_mode, "snapshot.injection_mode");
    this.requirePolling(record.modbus_polling, "snapshot.modbus_polling");
    const values = this.requireRecord(record.values, "snapshot.values");
    for (const [tag, value] of Object.entries(values)) {
      const signal = this.requireRecord(value, `snapshot.values.${tag}`);
      this.requireString(signal, "tag", `snapshot.values.${tag}`);
      this.requireString(signal, "quality", `snapshot.values.${tag}`);
    }
    const groups = this.requireRecord(record.groups, "snapshot.groups");
    if (!Array.isArray(groups.pumps)) {
      throw new Error("Contrato inválido: snapshot.groups.pumps debe ser una lista");
    }
    groups.pumps.forEach((value, index) => {
      const pump = this.requireRecord(value, `snapshot.groups.pumps[${index}]`);
      this.requireNumber(pump, "id", `snapshot.groups.pumps[${index}]`);
      const mode = this.requireString(pump, "emar_mode", `snapshot.groups.pumps[${index}]`);
      if (!["disabled", "automatic", "forced"].includes(mode)) {
        throw new Error(`Contrato inválido: snapshot.groups.pumps[${index}].emar_mode no es válido`);
      }
    });
    return record as unknown as RuntimeSnapshot;
  }

  public parseEmulator(payload: unknown): EmulatorState {
    return this.requireRecord(payload, "emulator") as EmulatorState;
  }

  public parseStream(payload: unknown): StreamPayload {
    const record = this.requireRecord(payload, "stream");
    if (record.type !== "state") {
      throw new Error("Contrato inválido: stream.type debe ser state");
    }
    return {
      type: "state",
      snapshot: this.parseSnapshot(record.snapshot),
      emulator: this.parseEmulator(record.emulator),
    };
  }

  public parseLogIndex(payload: unknown): LogIndex {
    const record = this.requireRecord(payload, "logs");
    const logDir = this.requireString(record, "log_dir", "logs");
    if (!Array.isArray(record.files)) {
      throw new Error("Contrato inválido: logs.files debe ser una lista");
    }
    return {
      log_dir: logDir,
      files: record.files.map((value, index) => {
        const file = this.requireRecord(value, `logs.files[${index}]`);
        return {
          name: this.requireString(file, "name", `logs.files[${index}]`),
          filename: this.requireString(file, "filename", `logs.files[${index}]`),
          size_bytes: this.requireNumber(file, "size_bytes", `logs.files[${index}]`),
        };
      }),
    };
  }

  public parseLogContent(payload: unknown): LogContent {
    const record = this.requireRecord(payload, "log");
    if (!Array.isArray(record.lines) || !record.lines.every((line) => typeof line === "string")) {
      throw new Error("Contrato inválido: log.lines debe ser una lista de textos");
    }
    return {
      name: this.requireString(record, "name", "log"),
      filename: this.requireString(record, "filename", "log"),
      exists: this.requireBoolean(record, "exists", "log"),
      lines: record.lines,
    };
  }

  private requireProject(payload: unknown, path: string): void {
    const project = this.requireRecord(payload, path);
    this.requireString(project, "name", path);
    this.requireString(project, "description", path);
  }

  private requirePolling(payload: unknown, path: string): void {
    const polling = this.requireRecord(payload, path);
    const functions = this.requireRecord(polling.functions, `${path}.functions`);
    for (const [code, value] of Object.entries(functions)) {
      const entry = this.requireRecord(value, `${path}.functions.${code}`);
      this.requireBoolean(entry, "enabled", `${path}.functions.${code}`);
      this.requireNumber(entry, "sample_rate_ms", `${path}.functions.${code}`);
    }
  }

  private requireRecord(payload: unknown, path: string): Record<string, unknown> {
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
      throw new Error(`Contrato inválido: ${path} debe ser un objeto`);
    }
    return payload as Record<string, unknown>;
  }

  private requireString(record: Record<string, unknown>, key: string, path: string): string {
    if (typeof record[key] !== "string") {
      throw new Error(`Contrato inválido: ${path}.${key} debe ser texto`);
    }
    return record[key];
  }

  private requireNumber(record: Record<string, unknown>, key: string, path: string): number {
    const value = record[key];
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new Error(`Contrato inválido: ${path}.${key} debe ser numérico`);
    }
    return value;
  }

  private requireBoolean(record: Record<string, unknown>, key: string, path: string): boolean {
    if (typeof record[key] !== "boolean") {
      throw new Error(`Contrato inválido: ${path}.${key} debe ser booleano`);
    }
    return record[key];
  }
}
