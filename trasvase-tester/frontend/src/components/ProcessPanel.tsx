import { Button, Card, StatusBadge } from "@servicoop/frontend-foundation";
import { useEffect, useState } from "react";

import { TrasvasePresenter } from "../TrasvasePresenter";
import type {
  EmulatorControlMode,
  EmulatorState,
  LevelHistory,
  RuntimeSnapshot,
} from "../TrasvaseModels";
import { LevelHistoryChart } from "./LevelHistoryChart";
import styles from "./ProcessPanel.module.css";

const CHAMBER = { height: 230, width: 360, x: 80, y: 530 } as const;
const RESERVE = { height: 460, width: 720, x: 650, y: 40 } as const;
const GROUND_Y = 500;

export interface ProcessPanelProps {
  emulator: EmulatorState;
  history: LevelHistory | null;
  onControl: (values: {
    mode?: EmulatorControlMode;
    season_position_pct?: number;
    inlet_open_pct?: number;
    outlet_open_pct?: number;
  }) => Promise<boolean>;
  presenter: TrasvasePresenter;
  snapshot: RuntimeSnapshot;
}

export function ProcessPanel({
  emulator,
  history,
  onControl,
  presenter,
  snapshot,
}: ProcessPanelProps) {
  const mode = emulator.control_mode ?? "manual";
  const [inlet, setInlet] = useState(emulator.manual_inlet_open_pct ?? emulator.inlet_open_pct ?? 0);
  const [outlet, setOutlet] = useState(emulator.manual_outlet_open_pct ?? emulator.outlet_open_pct ?? 0);
  const [season, setSeason] = useState(emulator.season_position_pct ?? 50);
  const [seasonEditing, setSeasonEditing] = useState(false);
  const [pendingSeason, setPendingSeason] = useState<number | null>(null);
  useEffect(
    () => setInlet(emulator.manual_inlet_open_pct ?? emulator.inlet_open_pct ?? 0),
    [emulator.inlet_open_pct, emulator.manual_inlet_open_pct],
  );
  useEffect(
    () => setOutlet(emulator.manual_outlet_open_pct ?? emulator.outlet_open_pct ?? 0),
    [emulator.manual_outlet_open_pct, emulator.outlet_open_pct],
  );
  useEffect(() => {
    const remoteSeason = emulator.season_position_pct ?? 50;
    if (seasonEditing) return;
    if (pendingSeason !== null) {
      if (Math.abs(remoteSeason - pendingSeason) < 0.05) {
        setSeason(remoteSeason);
        setPendingSeason(null);
      }
      return;
    }
    setSeason(remoteSeason);
  }, [emulator.season_position_pct, pendingSeason, seasonEditing]);

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
  const save = () => onControl({ inlet_open_pct: inlet, outlet_open_pct: outlet });
  const commitSeason = async () => {
    const nextSeason = season;
    if (pendingSeason !== null && Math.abs(pendingSeason - nextSeason) < 0.05) {
      setSeasonEditing(false);
      return;
    }
    setPendingSeason(nextSeason);
    setSeasonEditing(false);
    const saved = await onControl({ season_position_pct: nextSeason });
    if (!saved) setPendingSeason(null);
  };
  const seasonAngle = Math.PI - (season / 100) * Math.PI;
  const seasonMarker = {
    x: 120 + Math.cos(seasonAngle) * 90,
    y: 154 - Math.sin(seasonAngle) * 76,
  };
  const seasonLabel = season < 12.5 || season >= 87.5
    ? "Verano"
    : season < 37.5
      ? "Otoño"
      : season < 62.5
        ? "Invierno"
        : "Primavera";
  const chamberSignal = snapshot.values.eNvCamAsp;
  const reserveSignal = snapshot.values.eNvRes;

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
          <g className={styles.levelIndicator} transform={`translate(${CHAMBER.x + CHAMBER.width + 16} ${CHAMBER.y + 16})`}>
            <title>{chamberSignal ? `Calidad ${chamberSignal.quality} · fila ${chamberSignal.row} · ref ${chamberSignal.reference} · ${chamberSignal.age_s ?? "—"} s` : "Sin señal"}</title>
            <rect height="72" rx="9" width="178" />
            <text className={styles.indicatorLabel} textAnchor="end" x="162" y="21">NIVEL DE CÁMARA</text>
            <text className={styles.indicatorValue} textAnchor="end" x="162" y="48">{presenter.signalText(chamberSignal)}</text>
            <text className={styles.indicatorQuality} textAnchor="end" x="162" y="64">{chamberSignal?.quality ?? "unknown"}</text>
          </g>

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
          <g className={styles.levelIndicator} transform={`translate(${RESERVE.x - 194} ${RESERVE.y + 16})`}>
            <title>{reserveSignal ? `Calidad ${reserveSignal.quality} · fila ${reserveSignal.row} · ref ${reserveSignal.reference} · ${reserveSignal.age_s ?? "—"} s` : "Sin señal"}</title>
            <rect height="72" rx="9" width="178" />
            <text className={styles.indicatorLabel} x="16" y="21">NIVEL DE RESERVA</text>
            <text className={styles.indicatorValue} x="16" y="48">{presenter.signalText(reserveSignal)}</text>
            <text className={styles.indicatorQuality} x="16" y="64">{reserveSignal?.quality ?? "unknown"}</text>
          </g>

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
      <div className={styles.controlHeader}>
        <fieldset className={styles.modeSelector}>
          <legend>Modo de válvulas</legend>
          <label>
            <input
              checked={mode === "manual"}
              name="valve-control-mode"
              onChange={() => void onControl({ mode: "manual" })}
              type="radio"
            />
            Manual
          </label>
          <label>
            <input
              checked={mode === "automatic"}
              name="valve-control-mode"
              onChange={() => void onControl({ mode: "automatic" })}
              type="radio"
            />
            Automático
          </label>
        </fieldset>
        <div className={styles.simulatedClock}>
          <span>Día simulado</span>
          <strong>{emulator.simulated_clock?.display_time ?? "--:--:--"}</strong>
          <small>Un día completo por cada hora real</small>
        </div>
      </div>
      <div className={styles.valveControls}>
        <label className={styles.valve}>
          <span>Ingreso a cámara</span>
          <strong>{Math.round(emulator.inlet_open_pct ?? inlet)}%</strong>
          <small>{mode === "automatic" ? "Apertura calculada por estación" : "Apertura manual"}</small>
          <input
            disabled={mode === "automatic"}
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
          <strong>{Math.round(emulator.outlet_open_pct ?? outlet)}%</strong>
          <small>{mode === "automatic" ? "Demanda del horario simulado + jitter diario" : "Apertura manual"}</small>
          <input
            disabled={mode === "automatic"}
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
      <div className={styles.automaticControls}>
        <div className={styles.seasonCopy}>
          <h3>Disponibilidad estacional</h3>
          <p>El dial queda fijo en el servidor. Verano aplica 20%, los equinoccios 60% e invierno 100%, con transición continua.</p>
          <strong>{seasonLabel} · posición {season.toFixed(1)}%</strong>
        </div>
        <div className={styles.seasonDial}>
          <svg aria-label={`Estación seleccionada: ${seasonLabel}`} role="img" viewBox="0 0 240 210">
            <path className={styles.dialArc} d="M30 154 A90 76 0 0 1 210 154" />
            <line className={styles.dialHand} x1="120" x2={seasonMarker.x} y1="174" y2={seasonMarker.y} />
            <circle className={styles.dialMarker} cx={seasonMarker.x} cy={seasonMarker.y} r="8" />
            <text textAnchor="start" x="20" y="178">Verano</text>
            <text textAnchor="middle" x="57" y="88">Otoño · 60%</text>
            <text textAnchor="middle" x="120" y="44">Invierno · 100%</text>
            <text textAnchor="middle" x="183" y="88">Primavera · 60%</text>
            <text textAnchor="end" x="220" y="178">Verano</text>
            <text className={styles.summerCapacity} textAnchor="middle" x="120" y="198">20% en ambos extremos</text>
          </svg>
          <input
            aria-label="Posición continua en el ciclo de estaciones"
            max={100}
            min={0}
            onBlur={() => void commitSeason()}
            onChange={(event) => setSeason(event.target.valueAsNumber)}
            onKeyDown={() => setSeasonEditing(true)}
            onKeyUp={() => void commitSeason()}
            onPointerDown={() => setSeasonEditing(true)}
            onPointerUp={() => void commitSeason()}
            step={0.1}
            type="range"
            value={season}
          />
        </div>
      </div>
      {mode === "manual" && (
        <div className={styles.actions}>
          <Button onClick={() => void save()} variant="secondary">
            Aplicar válvulas manuales
          </Button>
        </div>
      )}
      <LevelHistoryChart
        chamberCeiling={chamberCeiling}
        chamberFloor={chamberFloor}
        history={history}
        reserveCeiling={reserveCeiling}
        reserveFloor={reserveFloor}
      />
    </Card>
  );
}
