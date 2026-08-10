import { Button, StatusBadge } from "@servicoop/frontend-foundation";

import type { RuntimeSnapshot, TesterConfig } from "../TrasvaseModels";
import type { StreamState } from "../TrasvaseStreamClient";
import { PollingControl } from "./PollingControl";
import styles from "./StatusHeader.module.css";

export interface StatusHeaderProps {
  config: TesterConfig;
  onPolling: (functionCode: string, values: { enabled?: boolean; sample_rate_ms?: number }) => Promise<void>;
  onWriteMode: () => Promise<void>;
  snapshot: RuntimeSnapshot;
  streamState: StreamState;
}

export function StatusHeader({ config, onPolling, onWriteMode, snapshot, streamState }: StatusHeaderProps) {
  const source = snapshot.connection.mode === "simulation"
    ? "Fuente: simulador"
    : `Fuente: PLC ${snapshot.controller.host} · ID ${snapshot.controller.unit_id}`;
  return (
    <header className={styles.header}>
      <div className={styles.introduction}>
        <div><p>{config.project}</p><h1>Trasvase Tester</h1><span>Operación Modbus/TCP y frontera de emulación</span></div>
        <div className={styles.statuses}>
          <StatusBadge tone={snapshot.connection.connected ? "success" : "danger"}>
            {snapshot.connection.connected ? "PLC conectado" : "PLC desconectado"}
          </StatusBadge>
          <StatusBadge tone={streamState === "connected" ? "success" : "warning"}>WEB {streamState}</StatusBadge>
          <StatusBadge tone={snapshot.connection.mode === "simulation" ? "warning" : "info"}>{source}</StatusBadge>
          <Button onClick={() => void onWriteMode()} variant={snapshot.write_mode.write_enabled ? "primary" : "secondary"}>
            {snapshot.write_mode.mode}
          </Button>
        </div>
      </div>
      <div className={styles.polling} aria-label="Control de lecturas Modbus">
        {["01", "02", "03", "04"].map((code) => {
          const control = snapshot.modbus_polling.functions[code] ?? config.modbus_polling.functions[code];
          return control ? <PollingControl control={control} functionCode={code} key={code} onUpdate={onPolling} /> : null;
        })}
      </div>
    </header>
  );
}
