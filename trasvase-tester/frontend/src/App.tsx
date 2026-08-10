import { AppShell } from "@servicoop/frontend-foundation";
import { useMemo } from "react";

import styles from "./App.module.css";
import { TrasvasePresenter } from "./TrasvasePresenter";
import { InjectionPanel } from "./components/InjectionPanel";
import { LogsPanel } from "./components/LogsPanel";
import { MetricGrid } from "./components/MetricGrid";
import { ProcessPanel } from "./components/ProcessPanel";
import { ProductionTables } from "./components/ProductionTables";
import { PumpGrid } from "./components/PumpGrid";
import { StatusHeader } from "./components/StatusHeader";
import { useTrasvaseData } from "./useTrasvaseData";

export function App() {
  const presenter = useMemo(() => new TrasvasePresenter(), []);
  const { client, config, emulator, error, execute, loading, logs, snapshot, streamState } = useTrasvaseData();

  return (
    <AppShell productName="Trasvase Tester" sectionName="Moto Tester">
      <main className={styles.main}>
        {error && <div className={styles.error} role="alert"><strong>Operación o contrato rechazado.</strong><span>{error}</span></div>}
        {loading && <p className={styles.loading}>Cargando configuración y estado operativo…</p>}
        {config && snapshot && (
          <>
            <StatusHeader
              config={config}
              onPolling={async (code, values) => { await execute(() => client.setPolling(code, values)); }}
              onInjectionMode={async () => {
                const next = snapshot.injection_mode.enabled ? "disabled" : "enabled";
                await execute(() => client.setInjectionMode(next));
              }}
              snapshot={snapshot}
              streamState={streamState}
            />
            <MetricGrid presenter={presenter} snapshot={snapshot} />
            {emulator && <ProcessPanel emulator={emulator} onValves={async (inlet, outlet) => { await execute(() => client.setValves(inlet, outlet)); }} presenter={presenter} snapshot={snapshot} />}
            <PumpGrid client={client} emulator={emulator} execute={execute} presenter={presenter} snapshot={snapshot} />
            <ProductionTables
              config={config}
              onSetpoint={async (tag, value) => { await execute(() => client.write(tag, value)); }}
              presenter={presenter}
              snapshot={snapshot}
            />
            <InjectionPanel client={client} config={config} execute={execute} presenter={presenter} snapshot={snapshot} />
            {logs && <LogsPanel client={client} logs={logs} />}
          </>
        )}
      </main>
    </AppShell>
  );
}
