import { Card, StatusBadge } from "@servicoop/frontend-foundation";

import { TrasvasePresenter } from "../TrasvasePresenter";
import type { RuntimeSnapshot } from "../TrasvaseModels";
import styles from "./MetricGrid.module.css";

export interface MetricGridProps { presenter: TrasvasePresenter; snapshot: RuntimeSnapshot; }

export function MetricGrid({ presenter, snapshot }: MetricGridProps) {
  const metrics = [
    ["eNvCamAsp", "Nivel cámara aspiración"],
    ["eNvRes", "Nivel reserva"],
    ["eTurb", "Turbiedad"],
  ] as const;
  return (
    <section className={styles.grid} aria-label="Variables principales">
      {metrics.map(([tag, label]) => {
        const signal = snapshot.values[tag];
        return (
          <Card className={styles.metric} key={tag}>
            <span>{label}</span><strong>{presenter.signalText(signal)}</strong>
            <StatusBadge className={styles.quality} tone={presenter.qualityTone(signal)}>{signal?.quality ?? "unknown"}</StatusBadge>
            <small>{signal ? `fila ${signal.row} · ref ${signal.reference} · ${signal.age_s ?? "—"} s` : "Sin señal"}</small>
          </Card>
        );
      })}
    </section>
  );
}
