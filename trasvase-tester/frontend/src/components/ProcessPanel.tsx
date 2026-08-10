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
  const chamberPercentage = percentage(chamber, chamberFloor, chamberCeiling);
  const reservePercentage = percentage(reserve, reserveFloor, reserveCeiling);
  const chamberWaterHeight = 176 * chamberPercentage / 100;
  const reserveWaterHeight = 104 * reservePercentage / 100;
  const save = () => onValves(inlet, outlet);

  return (
    <Card>
      <div className={styles.heading}>
        <div><h2>Emulador de campo</h2><p>Las válvulas gobiernan inyecciones y*; los niveles usan feedback del intercambio real.</p></div>
        <StatusBadge tone={emulator.last_error ? "danger" : emulator.injection_enabled === false ? "warning" : "success"}>
          {emulator.last_error ? "Emulador con error" : emulator.injection_enabled === false ? "Inyección y* deshabilitada" : "Inyección y* habilitada"}
        </StatusBadge>
      </div>
      <div className={styles.processViewport}>
        <svg className={styles.process} role="img" viewBox="0 0 1200 520">
          <title>Esquema hidráulico desde la cámara de aspiración enterrada hasta la reserva</title>
          <defs>
            <linearGradient id="processWater" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#4fc3f7" stopOpacity=".72" />
              <stop offset="1" stopColor="#0369a1" stopOpacity=".92" />
            </linearGradient>
            <marker id="flowArrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
              <path d="M0,0 L8,4 L0,8 Z" fill="currentColor" />
            </marker>
          </defs>

          <path className={styles.ground} d="M24 260 H1176" />
          <text className={styles.groundLabel} x="32" y="248">NIVEL DE SUELO · COTA 0</text>

          <path className={styles.pipe} d="M24 360 H76" markerEnd="url(#flowArrow)" />
          <text className={styles.pipeLabel} x="24" y="345">INGRESO</text>

          <path className={styles.tankOutline} d="M76 286 V476 H664 V286" />
          <rect fill="url(#processWater)" height={chamberWaterHeight} width="580" x="80" y={472 - chamberWaterHeight} />
          <path className={styles.waterLine} d={`M80 ${472 - chamberWaterHeight} H660`} />
          <text className={styles.equipmentLabel} x="96" y="444">CÁMARA DE ASPIRACIÓN · ENTERRADA</text>
          <text className={styles.valueLabel} x="96" y="466">Nivel {chamber}</text>

          <path className={styles.manifold} d="M250 106 H1016 V150" markerEnd="url(#flowArrow)" />
          <text className={styles.pipeLabel} x="680" y="92">MÚLTIPLE DE IMPULSIÓN A RESERVA</text>

          {snapshot.groups.pumps.map((pump, index) => {
            const visual = presenter.pumpVisual(pump, snapshot.connection.connected);
            const x = 250 + index * 90;
            return (
              <g key={pump.id}>
                <title>{`Bomba ${pump.id}: ${visual.label}`}</title>
                <path className={styles.dischargePipe} d={`M${x} 180 V106`} />
                <path className={styles.suctionPipe} d={`M${x} 244 V392`} />
                <path className={styles.strainer} d={`M${x - 13} 392 H${x + 13}`} />
                <image height="76" href={`assets/pump_${visual.image}.png`} preserveAspectRatio="xMidYMid meet" width="76" x={x - 38} y="184" />
                <text className={styles.pumpLabel} textAnchor="middle" x={x} y="278">B{pump.id}</text>
              </g>
            );
          })}

          <path className={styles.tankOutline} d="M900 150 V260 H1134 V150" />
          <rect fill="url(#processWater)" height={reserveWaterHeight} width="226" x="904" y={256 - reserveWaterHeight} />
          <path className={styles.waterLine} d={`M904 ${256 - reserveWaterHeight} H1130`} />
          <text className={styles.equipmentLabel} x="916" y="218">RESERVA</text>
          <text className={styles.valueLabel} x="916" y="242">Nivel {reserve}</text>
          <path className={styles.pipe} d="M1134 214 H1176" markerEnd="url(#flowArrow)" />
          <text className={styles.pipeLabel} x="1082" y="198">SALIDA</text>
        </svg>
      </div>
      <div className={styles.valveControls}>
        <label className={styles.valve}>
          <span>Ingreso a cámara</span><strong>{Math.round(inlet)}%</strong>
          <input max={100} min={0} onChange={(event) => setInlet(event.target.valueAsNumber)} onKeyUp={() => void save()} onPointerUp={() => void save()} type="range" value={inlet} />
        </label>
        <label className={styles.valve}>
          <span>Salida de reserva</span><strong>{Math.round(outlet)}%</strong>
          <input max={100} min={0} onChange={(event) => setOutlet(event.target.valueAsNumber)} onKeyUp={() => void save()} onPointerUp={() => void save()} type="range" value={outlet} />
        </label>
      </div>
      <div className={styles.actions}><Button onClick={() => void save()} variant="secondary">Aplicar válvulas</Button></div>
    </Card>
  );
}
