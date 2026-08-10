import { Button, Card, StatusBadge } from "@servicoop/frontend-foundation";
import { useState } from "react";

import type { TrasvaseApiClient } from "../TrasvaseApiClient";
import { TrasvasePresenter } from "../TrasvasePresenter";
import type { RuntimeSnapshot, SignalDefinition, TesterConfig } from "../TrasvaseModels";
import styles from "./InjectionPanel.module.css";

export interface InjectionPanelProps {
  client: TrasvaseApiClient;
  config: TesterConfig;
  execute: (operation: () => Promise<unknown>) => Promise<boolean>;
  presenter: TrasvasePresenter;
  snapshot: RuntimeSnapshot;
}

export function InjectionPanel({ client, config, execute, presenter, snapshot }: InjectionPanelProps) {
  const [filter, setFilter] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const target = (signal: SignalDefinition) => {
    if (!signal.injects_tag) return "—";
    const match = Object.values(config.tables).flatMap((table) => table.signals).find((item) => item.tag === signal.injects_tag);
    return match ? `${match.tag} · fila ${match.row}` : signal.injects_tag;
  };
  const signals = (name: string) => (config.tables[name]?.signals ?? [])
    .filter((signal) => signal.facade)
    .filter((signal) => !filter || `${signal.tag} ${signal.label} ${signal.injects_tag ?? ""}`.toLowerCase().includes(filter.toLowerCase()))
    .sort((left, right) => left.row - right.row);
  const injectNumber = (signal: SignalDefinition) => {
    const raw = drafts[signal.tag] ?? String(snapshot.values[signal.tag]?.value ?? "");
    const value = Number(raw);
    if (!Number.isFinite(value)) return;
    void execute(() => client.inject(signal.tag, value));
  };
  const table = (name: "analog_setpoints" | "digital_commands", label: string) => (
    <Card className={styles.window}>
      <h3>{label}</h3>
      <div className={styles.scroll}><table>
        <thead><tr><th>Fila</th><th>Tag</th><th>Destino</th><th>Valor</th><th>Set</th><th /></tr></thead>
        <tbody>{signals(name).map((signal) => {
          const value = snapshot.values[signal.tag];
          const digital = name === "digital_commands" || signal.write_kind === "coil";
          return (
            <tr key={signal.tag}>
              <td>{signal.row}</td><td title={signal.label}>{signal.tag}</td><td>{target(signal)}</td>
              <td><strong>{presenter.signalText(value)}</strong> <StatusBadge tone={presenter.qualityTone(value)}>{value?.quality ?? "unknown"}</StatusBadge></td>
              <td>{digital
                ? <input aria-label={`Inyectar ${signal.tag}`} checked={presenter.signalBoolean(value)} onChange={(event) => void execute(() => client.inject(signal.tag, event.target.checked))} type="checkbox" />
                : <input aria-label={`Valor ${signal.tag}`} onChange={(event) => setDrafts((current) => ({ ...current, [signal.tag]: event.target.value }))} step={1} type="number" value={drafts[signal.tag] ?? String(value?.value ?? "")} />}
              </td>
              <td>{!digital && <Button onClick={() => injectNumber(signal)} variant="ghost">Aplicar</Button>}</td>
            </tr>
          );
        })}</tbody>
      </table></div>
    </Card>
  );
  return (
    <section>
      <div className={styles.heading}><div><h2>Inyecciones</h2><p>Entradas de emulación separadas del mapa de producción.</p></div><input onChange={(event) => setFilter(event.target.value)} placeholder="Filtrar y*" type="search" value={filter} /></div>
      <div className={styles.grid}>{table("analog_setpoints", "Inyección lectura AN")}{table("digital_commands", "Inyección lectura DI")}</div>
    </section>
  );
}
