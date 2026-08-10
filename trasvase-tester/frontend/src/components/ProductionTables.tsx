import { Card, StatusBadge } from "@servicoop/frontend-foundation";

import { TrasvasePresenter } from "../TrasvasePresenter";
import type { RuntimeSnapshot, TableDefinition, TesterConfig } from "../TrasvaseModels";
import styles from "./ProductionTables.module.css";

export const TABLE_ORDER = ["analog_reads", "analog_setpoints", "digital_reads", "digital_commands"] as const;

export interface ProductionTablesProps {
  config: TesterConfig;
  presenter: TrasvasePresenter;
  snapshot: RuntimeSnapshot;
}

export function ProductionTables({ config, presenter, snapshot }: ProductionTablesProps) {
  const rows = (table: TableDefinition) => {
    const signals = table.signals.filter((signal) => !signal.facade);
    const byRow = new Map(signals.map((signal) => [signal.row, signal]));
    const maximum = signals.length === 0 ? -1 : Math.max(...signals.map((signal) => signal.row));
    return Array.from({ length: maximum + 1 }, (_, row) => ({ row, signal: byRow.get(row) }));
  };
  return (
    <section>
      <div className={styles.heading}><h2>Tablas SCA de producción</h2><p>Lecturas reales; las fachadas de inyección se muestran por separado.</p></div>
      <div className={styles.grid}>
        {TABLE_ORDER.map((name) => {
          const table = config.tables[name];
          if (!table) return null;
          const production = table.signals.filter((signal) => !signal.facade);
          const fc = production[0]?.function_code ?? "—";
          const lastRow = production.length > 0 ? Math.max(...production.map((signal) => signal.row)) : "—";
          return (
            <Card className={styles.window} key={name}>
              <div className={styles.title}><strong>{table.label}</strong><span>FC{fc} · inicio {table.start_ref} · offset {table.start_pdu} · prod 0..{lastRow}</span></div>
              <div className={styles.scroll}>
                <table><thead><tr><th>Fila</th><th>Tag</th><th>Valor</th></tr></thead>
                  <tbody>{rows(table).map(({ row, signal }) => {
                    const value = signal ? snapshot.values[signal.tag] : undefined;
                    return (
                      <tr className={signal ? undefined : styles.empty} key={row}>
                        <td>{row}</td><td title={signal?.label}>{signal?.tag}</td>
                        <td>{signal && <><strong>{presenter.signalText(value)}</strong> <StatusBadge tone={presenter.qualityTone(value)}>{value?.quality ?? "unknown"}</StatusBadge></>}</td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
