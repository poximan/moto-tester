import type { StatusTone } from "@servicoop/frontend-foundation";

import type { PumpSnapshot, SignalValue } from "./TrasvaseModels";

export interface PumpVisual {
  image: "blue" | "gray" | "green" | "red";
  label: string;
  tone: StatusTone;
}

export class TrasvasePresenter {
  public signalBoolean(signal: SignalValue | boolean | number | string | null | undefined): boolean {
    const value = typeof signal === "object" && signal !== null && "value" in signal ? signal.value : signal;
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string") return ["1", "true", "on", "si", "sí"].includes(value.toLowerCase());
    return false;
  }

  public signalText(signal: SignalValue | null | undefined): string {
    if (signal?.value === null || signal?.value === undefined) return "—";
    if (typeof signal.value === "boolean") return signal.value ? "1" : "0";
    return String(signal.value);
  }

  public signalNumber(signal: SignalValue | null | undefined, fallback: number): number {
    const value = Number(signal?.value);
    return Number.isFinite(value) ? value : fallback;
  }

  public qualityTone(signal: SignalValue | null | undefined): StatusTone {
    return {
      error: "danger",
      good: "success",
      local: "info",
      stale: "warning",
      unknown: "neutral",
    }[signal?.quality ?? "unknown"] as StatusTone;
  }

  public injectionStatusText(signal: SignalValue | null | undefined): string {
    if (!signal || signal.quality === "unknown") return "Sin envío";
    if (signal.quality === "error") return "Error";
    if (signal.error?.includes("no escrita")) return "No enviado";
    if (signal.quality === "local" && signal.error === "write queued") return "Pendiente";
    if (signal.quality === "local") return "Valor inicial";
    return "Enviado";
  }

  public injectionStatusTone(signal: SignalValue | null | undefined): StatusTone {
    if (signal?.quality === "error") return "danger";
    if (signal?.error?.includes("no escrita")) return "warning";
    if (signal?.quality === "local" && signal.error === "write queued") return "info";
    if (signal?.quality === "good" || signal?.quality === "stale") return "success";
    return "neutral";
  }

  public pumpVisual(pump: PumpSnapshot, connected: boolean): PumpVisual {
    if (!connected) return { image: "gray", label: "Sin conexión", tone: "neutral" };
    if (!this.signalBoolean(pump.ok)) return { image: "red", label: "Falla", tone: "danger" };
    if (this.signalBoolean(pump.running)) return { image: "green", label: "En marcha", tone: "success" };
    return { image: "blue", label: "Detenida", tone: "info" };
  }
}
