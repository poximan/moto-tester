import { AppShell, StartupSplash } from "@servicoop/frontend-foundation";
import { useMemo } from "react";

import styles from "./App.module.css";
import { TrasvasePresenter } from "./TrasvasePresenter";
import { InjectionPanel } from "./components/InjectionPanel";
import { LogsPanel } from "./components/LogsPanel";
import { ProcessPanel } from "./components/ProcessPanel";
import { ProductionTables } from "./components/ProductionTables";
import { PumpGrid } from "./components/PumpGrid";
import { StatusHeader } from "./components/StatusHeader";
import { useTrasvaseData } from "./useTrasvaseData";

export function App() {
  const presenter = useMemo(() => new TrasvasePresenter(), []);
  const { client, config, emulator, error, execute, levelHistory, loading, snapshot, streamState } = useTrasvaseData();

  return (
    <StartupSplash productName="moto-tester" logoSrc={`${import.meta.env.BASE_URL}assets/trasvase.png`}
      ready={!loading || error !== null}>
      <AppShell productName="Trasvase Tester" sectionName="Moto Tester">
        <main className={`sc-page ${styles.main}`}>
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
              {emulator && <ProcessPanel emulator={emulator} history={levelHistory} onControl={async (values) => execute(() => client.setEmulatorControl(values))} presenter={presenter} snapshot={snapshot} />}
              <PumpGrid client={client} execute={execute} presenter={presenter} snapshot={snapshot} />
              <ProductionTables
                config={config}
                onSetpoint={async (tag, value) => { await execute(() => client.write(tag, value)); }}
                presenter={presenter}
                snapshot={snapshot}
              />
              <InjectionPanel client={client} config={config} execute={execute} presenter={presenter} snapshot={snapshot} />
              <LogsPanel client={client} />
            </>
          )}
        </main>
      </AppShell>
    </StartupSplash>
  );
}
