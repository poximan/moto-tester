import { Button, Card, StatusBadge } from "@servicoop/frontend-foundation";
import { useEffect, useRef, useState } from "react";

import type { TrasvaseApiClient } from "../TrasvaseApiClient";
import { TrasvasePresenter } from "../TrasvasePresenter";
import type { PumpSnapshot, SignalValue } from "../TrasvaseModels";
import styles from "./PumpCard.module.css";

export interface PumpCardProps {
  client: TrasvaseApiClient;
  connected: boolean;
  execute: (operation: () => Promise<unknown>) => Promise<boolean>;
  presenter: TrasvasePresenter;
  pump: PumpSnapshot;
  rtuSelection: SignalValue | undefined;
}

export function PumpCard({ client, connected, execute, presenter, pump, rtuSelection }: PumpCardProps) {
  const storageKey = `generate-emar-${pump.id}`;
  const [generateEmar, setGenerateEmar] = useState(() => localStorage.getItem(storageKey) === "1");
  const lastGenerated = useRef<boolean | null>(null);
  const generating = useRef(false);
  const visual = presenter.pumpVisual(pump, connected);
  const rtu = presenter.signalBoolean(rtuSelection?.value == null ? pump.rtu : rtuSelection);
  const automatic = presenter.signalBoolean(pump.cmd_aut);

  useEffect(() => {
    localStorage.setItem(storageKey, generateEmar ? "1" : "0");
    if (!generateEmar) lastGenerated.current = null;
  }, [generateEmar, storageKey]);

  useEffect(() => {
    if (!generateEmar || pump.arr?.value === null || pump.arr?.value === undefined || generating.current) return;
    const next = presenter.signalBoolean(pump.arr);
    if (lastGenerated.current === next) return;
    generating.current = true;
    void execute(() => client.inject(`yB${pump.id}EMar`, next, "web-generar-emar")).then((ok) => {
      if (ok) lastGenerated.current = next;
      generating.current = false;
    });
  }, [client, execute, generateEmar, presenter, pump.arr, pump.id]);

  const command = (values: { aut?: boolean; mr?: boolean }) => execute(() => client.sendPump(pump.id, values));
  const indicator = (label: string, active: boolean, danger = false) => (
    <span><i className={active ? danger ? styles.danger : styles.on : styles.off} />{label}</span>
  );

  return (
    <Card className={styles.card}>
      <div className={styles.heading}><h3>Bomba {pump.id}</h3><StatusBadge tone={visual.tone}>{visual.label}</StatusBadge></div>
      <img alt={`Bomba ${pump.id}: ${visual.label}`} className={styles.image} src={`assets/pump_${visual.image}.png`} />
      <strong className={styles.hours}>{presenter.signalText(pump.hours)} h</strong>
      <div className={styles.indicators}>
        {indicator("RTU", rtu)}{indicator("Automático", presenter.signalBoolean(pump.aut))}
        {indicator("Salud", presenter.signalBoolean(pump.ok))}{indicator("EMar", presenter.signalBoolean(pump.running))}
        {indicator("Interlock", presenter.signalBoolean(pump.interlock), true)}{indicator("Falla", presenter.signalBoolean(pump.fault), true)}
      </div>
      <div className={styles.options}>
        <label><input checked={generateEmar} onChange={(event) => setGenerateEmar(event.target.checked)} type="checkbox" /> generar EMar</label>
        <Button onClick={() => void execute(() => client.inject(`yB${pump.id}RTU`, !rtu))} variant="ghost">{rtu ? "RTU" : "Tablero"}</Button>
      </div>
      <div className={styles.commands}>
        <Button onClick={() => void command({ aut: !automatic })} variant="secondary">{automatic ? "Auto" : "Man"}</Button>
        <Button onClick={() => void command({ mr: true })}>Marcha</Button>
        <Button onClick={() => void command({ mr: false })} variant="secondary">Parada</Button>
      </div>
    </Card>
  );
}
