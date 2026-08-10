import { Button, Card, StatusBadge } from "@servicoop/frontend-foundation";
import { useEffect, useState } from "react";

import { TrasvasePresenter } from "../TrasvasePresenter";
import type { EmulatorState, RuntimeSnapshot } from "../TrasvaseModels";
import styles from "./ProcessPanel.module.css";

const CHAMBER = { height: 230, width: 360, x: 80, y: 530 } as const;
const RESERVE = { height: 460, width: 720, x: 650, y: 40 } as const;
const GROUND_Y = 500;

export interface ProcessPanelProps {
  emulator: EmulatorState;
  onValves: (inlet: number, outlet: number) => Promise<void>;
  presenter: TrasvasePresenter;
  snapshot: RuntimeSnapshot;
}

export function ProcessPanel({
  emulator,
  onValves,
  presenter,
  snapshot,
}: ProcessPanelProps) {
  const [inlet, setInlet] = useState(emulator.inlet_open_pct ?? 0);
  const [outlet, setOutlet] = useState(emulator.outlet_open_pct ?? 0);
  useEffect(
    () => setInlet(emulator.inlet_open_pct ?? 0),
    [emulator.inlet_open_pct],
  );
  useEffect(
    () => setOutlet(emulator.outlet_open_pct ?? 0),
    [emulator.outlet_open_pct],
  );

  const chamber = presenter.signalNumber(
    snapshot.values.eNvCamAsp,
    emulator.yNvCamAsp ?? 0,
  );
  const reserve = presenter.signalNumber(
    snapshot.values.eNvRes,
    emulator.yNvRes ?? 0,
  );
  const chamberFloor = presenter.signalNumber(
    snapshot.values.gCamFn,
    emulator.bounds?.yNvCamAsp?.floor ?? 0,
  );
  const chamberCeiling = presenter.signalNumber(
    snapshot.values.gCamRb,
    emulator.bounds?.yNvCamAsp?.ceiling ?? 4_000,
  );
  const reserveFloor = presenter.signalNumber(
    snapshot.values.gResFn,
    emulator.bounds?.yNvRes?.floor ?? -1,
  );
  const reserveCeiling = presenter.signalNumber(
    snapshot.values.gResSp,
    emulator.bounds?.yNvRes?.ceiling ?? 6_000,
  );
  const percentage = (value: number, floor: number, ceiling: number) => {
    const span = Math.max(Math.abs(ceiling - floor), 1);
    return Math.max(3, Math.min(94, ((value - floor) / span) * 100));
  };
  const chamberPercentage = percentage(chamber, chamberFloor, chamberCeiling);
  const reservePercentage = percentage(reserve, reserveFloor, reserveCeiling);
  const chamberWaterHeight = ((CHAMBER.height - 8) * chamberPercentage) / 100;
  const reserveWaterHeight = ((RESERVE.height - 8) * reservePercentage) / 100;
  const pumps = snapshot.groups.pumps.map((pump) => ({
    active:
      snapshot.connection.connected && presenter.signalBoolean(pump.running),
    pump,
    visual: presenter.pumpVisual(pump, snapshot.connection.connected),
  }));
  const manifoldActive = pumps.some(({ active }) => active);
  const pipeClass = (baseClass: string, active: boolean) =>
    `${baseClass} ${active ? styles.activePipe : styles.idlePipe}`;
  const save = () => onValves(inlet, outlet);

  return (
    <Card>
      <div className={styles.heading}>
        <h2>Emulador de campo</h2>
        <StatusBadge
          tone={
            emulator.last_error
              ? "danger"
              : emulator.injection_enabled === false
                ? "warning"
                : "success"
          }
        >
          {emulator.last_error
            ? "Emulador con error"
            : emulator.injection_enabled === false
              ? "Inyección y* deshabilitada"
              : "Inyección y* habilitada"}
        </StatusBadge>
      </div>
      <div className={styles.processViewport}>
        <svg className={styles.process} role="img" viewBox="0 0 1450 800">
          <title>
            Esquema hidráulico desde la cámara de aspiración enterrada hasta la
            reserva
          </title>
          <defs>
            <linearGradient id="processWater" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#4fc3f7" stopOpacity=".72" />
              <stop offset="1" stopColor="#0369a1" stopOpacity=".92" />
            </linearGradient>
            <marker
              id="flowArrow"
              markerHeight="9"
              markerUnits="userSpaceOnUse"
              markerWidth="9"
              orient="auto"
              refX="8"
              refY="4.5"
              viewBox="0 0 9 9"
            >
              <path d="M0,0 L9,4.5 L0,9 Z" fill="context-stroke" />
            </marker>
          </defs>

          <path className={styles.ground} d={`M40 ${GROUND_Y} H1410`} />

          <path
            className={`${styles.pipe} ${styles.idlePipe}`}
            d="M24 620 H80"
            markerEnd="url(#flowArrow)"
          />
          <text className={styles.pipeLabel} x="24" y="602">
            INGRESO
          </text>

          <path
            className={styles.tankOutline}
            d={`M${CHAMBER.x} ${CHAMBER.y} V${CHAMBER.y + CHAMBER.height} H${CHAMBER.x + CHAMBER.width} V${CHAMBER.y}`}
          />
          <rect
            fill="url(#processWater)"
            height={chamberWaterHeight}
            width={CHAMBER.width - 8}
            x={CHAMBER.x + 4}
            y={CHAMBER.y + CHAMBER.height - 4 - chamberWaterHeight}
          />
          <path
            className={styles.waterLine}
            d={`M${CHAMBER.x + 4} ${CHAMBER.y + CHAMBER.height - 4 - chamberWaterHeight} H${CHAMBER.x + CHAMBER.width - 4}`}
          />

          <rect
            className={styles.closedTank}
            height={RESERVE.height}
            width={RESERVE.width}
            x={RESERVE.x}
            y={RESERVE.y}
          />
          <rect
            fill="url(#processWater)"
            height={reserveWaterHeight}
            width={RESERVE.width - 8}
            x={RESERVE.x + 4}
            y={RESERVE.y + RESERVE.height - 4 - reserveWaterHeight}
          />
          <path
            className={styles.waterLine}
            d={`M${RESERVE.x + 4} ${RESERVE.y + RESERVE.height - 4 - reserveWaterHeight} H${RESERVE.x + RESERVE.width - 4}`}
          />

          <path
            className={pipeClass(styles.manifold!, manifoldActive)}
            d={`M120 270 H${RESERVE.x + 14}`}
            markerEnd="url(#flowArrow)"
          />
          <text
            className={styles.pipeLabel}
            textAnchor="middle"
            x="385"
            y="250"
          >
            MÚLTIPLE DE IMPULSIÓN A RESERVA
          </text>

          {pumps.map(({ active, pump, visual }, index) => {
            const x = 120 + index * 70;
            return (
              <g key={pump.id}>
                <title>{`Bomba ${pump.id}: ${visual.label}`}</title>
                <path
                  className={pipeClass(styles.dischargePipe!, active)}
                  d={`M${x} 426 V270`}
                />
                <path
                  className={pipeClass(styles.suctionPipe!, active)}
                  d={`M${x} 498 V742`}
                />
                <path
                  className={pipeClass(styles.strainer!, active)}
                  d={`M${x - 13} 742 H${x + 13}`}
                />
                <image
                  height="76"
                  href={`assets/pump_${visual.image}.png`}
                  preserveAspectRatio="xMidYMid meet"
                  width="76"
                  x={x - 38}
                  y="426"
                />
                <text
                  className={styles.pumpLabel}
                  textAnchor="middle"
                  x={x}
                  y="520"
                >
                  B{pump.id}
                </text>
              </g>
            );
          })}

          <path
            className={`${styles.pipe} ${styles.idlePipe}`}
            d={`M${RESERVE.x + RESERVE.width} 380 H1410`}
            markerEnd="url(#flowArrow)"
          />
          <text className={styles.pipeLabel} x="1320" y="360">
            SALIDA
          </text>
        </svg>
      </div>
      <div className={styles.valveControls}>
        <label className={styles.valve}>
          <span>Ingreso a cámara</span>
          <strong>{Math.round(inlet)}%</strong>
          <input
            max={100}
            min={0}
            onChange={(event) => setInlet(event.target.valueAsNumber)}
            onKeyUp={() => void save()}
            onPointerUp={() => void save()}
            type="range"
            value={inlet}
          />
        </label>
        <label className={styles.valve}>
          <span>Salida de reserva</span>
          <strong>{Math.round(outlet)}%</strong>
          <input
            max={100}
            min={0}
            onChange={(event) => setOutlet(event.target.valueAsNumber)}
            onKeyUp={() => void save()}
            onPointerUp={() => void save()}
            type="range"
            value={outlet}
          />
        </label>
      </div>
      <div className={styles.actions}>
        <Button onClick={() => void save()} variant="secondary">
          Aplicar válvulas
        </Button>
      </div>
    </Card>
  );
}
