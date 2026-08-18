import { TrasvaseContractParser } from "./TrasvaseContractParser";
import type {
  EmulatorState,
  LogContent,
  LogIndex,
  RuntimeSnapshot,
  TesterConfig,
  EmarMode,
  InjectionModeName,
} from "./TrasvaseModels";

export class TrasvaseApiClient {
  public constructor(
    private readonly baseUrl: URL,
    private readonly parser = new TrasvaseContractParser(),
  ) {}

  public get streamUrl(): URL {
    const url = new URL("ws/stream", this.baseUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url;
  }

  public async getConfig(signal?: AbortSignal): Promise<TesterConfig> {
    return this.parser.parseConfig(await this.getJson("api/config", signal));
  }

  public async getSnapshot(signal?: AbortSignal): Promise<RuntimeSnapshot> {
    return this.parser.parseSnapshot(await this.getJson("api/snapshot", signal));
  }

  public async getEmulator(signal?: AbortSignal): Promise<EmulatorState> {
    return this.parser.parseEmulator(await this.getJson("api/emulator/state", signal));
  }

  public async getLogs(signal?: AbortSignal): Promise<LogIndex> {
    return this.parser.parseLogIndex(await this.getJson("api/logs", signal));
  }

  public async getLog(name: string, lines: number, signal?: AbortSignal): Promise<LogContent> {
    return this.parser.parseLogContent(
      await this.getJson(`api/logs/${encodeURIComponent(name)}?lines=${encodeURIComponent(lines)}`, signal),
    );
  }

  public async getDiagnostics(signal?: AbortSignal): Promise<Record<string, unknown>> {
    const payload = await this.getJson("api/diagnostics", signal);
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
      throw new Error("Contrato inválido: diagnostics debe ser un objeto");
    }
    return payload as Record<string, unknown>;
  }

  public setInjectionMode(mode: InjectionModeName): Promise<unknown> {
    return this.sendJson("api/injection-mode", "PUT", { mode, source: "web" });
  }

  public setPolling(functionCode: string, values: { enabled?: boolean; sample_rate_ms?: number }): Promise<unknown> {
    return this.sendJson(`api/modbus-polling/${encodeURIComponent(functionCode)}`, "PUT", { ...values, source: "web" });
  }

  public sendPump(pump: number, values: { aut?: boolean; mr?: boolean }): Promise<unknown> {
    return this.sendJson(`api/pumps/${pump}/command`, "POST", { ...values, source: "web" });
  }

  public inject(tag: string, value: boolean | number, source = "web"): Promise<unknown> {
    return this.sendJson("api/injection", "POST", { values: { [tag]: value }, source });
  }

  public write(tag: string, value: boolean | number, source = "web"): Promise<unknown> {
    return this.sendJson("api/write", "POST", { tag, value, source });
  }

  public async setValves(inlet: number, outlet: number): Promise<EmulatorState> {
    return this.parser.parseEmulator(await this.sendJson("api/emulator/valves", "PUT", {
      inlet_open_pct: inlet,
      outlet_open_pct: outlet,
    }));
  }

  public setEmarMode(pump: number, mode: EmarMode): Promise<unknown> {
    return this.sendJson(`api/pumps/${pump}/emar-mode`, "PUT", { mode });
  }

  private async getJson(relativePath: string, signal?: AbortSignal): Promise<unknown> {
    const response = await fetch(new URL(relativePath, this.baseUrl), {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal,
    });
    return this.readResponse(response, relativePath);
  }

  private async sendJson(relativePath: string, method: "POST" | "PUT", body: unknown): Promise<unknown> {
    const response = await fetch(new URL(relativePath, this.baseUrl), {
      body: JSON.stringify(body),
      credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      method,
    });
    return this.readResponse(response, relativePath);
  }

  private async readResponse(response: Response, relativePath: string): Promise<unknown> {
    if (!response.ok) {
      throw new Error(`${relativePath} respondió HTTP ${response.status}: ${await response.text()}`);
    }
    return response.json() as Promise<unknown>;
  }
}
