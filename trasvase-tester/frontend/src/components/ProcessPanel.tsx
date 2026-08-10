import { Button, Card, StatusBadge } from "@servicoop/frontend-foundation";
import { useEffect, useState } from "react";

import { TrasvasePresenter } from "../TrasvasePresenter";
import type { EmulatorState, RuntimeSnapshot } from "../TrasvaseModels";
import styles from "./ProcessPanel.module.css";

export interface ProcessPanelProps {
  emulator: EmulatorState;
  onValves: (inlet: number, outlet: number) => Promise<void>;
  presenter: TrasvasePresenter;
  snapshot: RuntimeSnapshot;
}

export function ProcessPanel({ emulator, onValves, presenter, snapshot }: ProcessPanelProps) {
  const [inlet, setInlet] = useState(emulator.inlet_open_pct ?? 0);
  const [outlet, setOutlet] = useState(emulator.outlet_open_pct ?? 0);
  useEffect(() => setInlet(emulator.inlet_open_pct ?? 0), [emulator.inlet_open_pct]);
  useEffect(() => setOutlet(emulator.outlet_open_pct ?? 0), [emulator.outlet_open_pct]);

  const chamber = presenter.signalNumber(snapshot.values.eNvCamAsp, emulator.yNvCamAsp ?? 0);
  const reserve = presenter.signalNumber(snapshot.values.eNvRes, emulator.yNvRes ?? 0);
  const chamberFloor = presenter.signalNumber(snapshot.values.gCamFn, emulator.bounds?.yNvCamAsp?.floor ?? 0);
  const chamberCeiling = presenter.signalNumber(snapshot.values.gCamRb, emulator.bounds?.yNvCamAsp?.ceiling ?? 4_000);
  const reserveFloor = presenter.signalNumber(snapshot.values.gResFn, emulator.bounds?.yNvRes?.floor ?? -1);
  const reserveCeiling = presenter.signalNumber(snapshot.values.gResSp, emulator.bounds?.yNvRes?.ceiling ?? 6_000);
  const percentage = (value: number, floor: number, ceiling: number) => {
    const span = Math.max(Math.abs(ceiling - floor), 1);
    return Math.max(3, Math.min(94, ((value - floor) / span) * 100));
  };
  const save = () => onValves(inlet, outlet);

  return (
    <Card>
      <div className={styles.heading}>
        <div><h2>Emulador de campo</h2><p>Las válvulas gobiernan inyecciones y*; los niveles usan feedback del intercambio real.</p></div>
        <StatusBadge tone={emulator.last_error ? "danger" : emulator.injection_enabled === false ? "warning" : "success"}>
          {emulator.last_error ? "Emulador con error" : emulator.injection_enabled === false ? "Inyección y* deshabilitada" : "Inyección y* habilitada"}
        </StatusBadge>
      </div>
      <div className={styles.process}>
        <label className={styles.valve}>
          <span>Ingreso cámara</span><strong>{Math.round(inlet)}%</strong>
          <input max={100} min={0} onChange={(event) => setInlet(event.target.valueAsNumber)} onKeyUp={() => void save()} onPointerUp={() => void save()} type="range" value={inlet} />
        </label>
        <div className={styles.tank}>
          <div className={styles.water} style={{ height: `${percentage(chamber, chamberFloor, chamberCeiling)}%` }} />
          <span>Cámara aspiración</span><strong>{chamber}</strong>
        </div>
        <div className={styles.pumpBank}>
          {snapshot.groups.pumps.map((pump) => {
            const visual = presenter.pumpVisual(pump, snapshot.connection.connected);
            return <img alt={`Bomba ${pump.id}: ${visual.label}`} key={pump.id} src={`assets/pump_${visual.image}.png`} title={visual.label} />;
          })}
          <span>Bombas de trasvase</span>
        </div>
        <div className={styles.tank}>
          <div className={styles.water} style={{ height: `${percentage(reserve, reserveFloor, reserveCeiling)}%` }} />
          <span>Reserva</span><strong>{reserve}</strong>
        </div>
        <label className={styles.valve}>
          <span>Salida reserva</span><strong>{Math.round(outlet)}%</strong>
          <input max={100} min={0} onChange={(event) => setOutlet(event.target.valueAsNumber)} onKeyUp={() => void save()} onPointerUp={() => void save()} type="range" value={outlet} />
        </label>
      </div>
      <div className={styles.actions}><Button onClick={() => void save()} variant="secondary">Aplicar válvulas</Button></div>
    </Card>
  );
}
