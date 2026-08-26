import { useState, type PointerEvent } from "react";

import type { LevelHistory, LevelHistoryPoint } from "../TrasvaseModels";
import styles from "./LevelHistoryChart.module.css";

const WIDTH = 900;
const HEIGHT = 220;
const LEFT = 70;
const RIGHT = 18;
const TOP = 18;
const BOTTOM = 38;
const TOOLTIP_WIDTH = 260;
const TOOLTIP_HEIGHT = 52;

const timestampFormatter = new Intl.DateTimeFormat("es-AR", {
  dateStyle: "short",
  hour12: false,
  timeStyle: "medium",
  timeZone: "Etc/GMT+3",
});

interface LineChartProps {
  ceiling: number;
  colorClass: string;
  floor: number;
  label: string;
  points: LevelHistoryPoint[];
  value: (point: LevelHistoryPoint) => number;
}

function LineChart({ ceiling, colorClass, floor, label, points, value }: LineChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const first = points[0];
  const last = points.at(-1);
  if (!first || !last) {
    return <div className={styles.empty}>Todavía no hay muestras para {label.toLowerCase()}.</div>;
  }
  const timeSpan = Math.max(last.timestamp_real - first.timestamp_real, 1);
  const valueSpan = Math.max(ceiling - floor, 1);
  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const coordinates = points.map((point) => {
    const x = LEFT + ((point.timestamp_real - first.timestamp_real) / timeSpan) * plotWidth;
    const normalized = Math.max(0, Math.min(1, (value(point) - floor) / valueSpan));
    const y = TOP + (1 - normalized) * plotHeight;
    return { x, y };
  });
  const polylinePoints = coordinates.map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const simulatedDays = Math.max(0, (last.timestamp_real - first.timestamp_real) / 3600);
  const hoveredPoint = hoveredIndex === null ? undefined : points[hoveredIndex];
  const hoveredCoordinate = hoveredIndex === null ? undefined : coordinates[hoveredIndex];
  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * WIDTH;
    const pointerX = Math.max(LEFT, Math.min(WIDTH - RIGHT, svgX));
    const targetTimestamp = first.timestamp_real + ((pointerX - LEFT) / plotWidth) * timeSpan;
    let nearestIndex = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    points.forEach((point, index) => {
      const distance = Math.abs(point.timestamp_real - targetTimestamp);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });
    setHoveredIndex(nearestIndex);
  };
  const tooltipX = hoveredCoordinate
    ? Math.max(LEFT, Math.min(WIDTH - RIGHT - TOOLTIP_WIDTH, hoveredCoordinate.x + 12))
    : LEFT;
  const tooltipY = hoveredCoordinate
    ? hoveredCoordinate.y > TOP + TOOLTIP_HEIGHT + 8
      ? hoveredCoordinate.y - TOOLTIP_HEIGHT - 8
      : hoveredCoordinate.y + 12
    : TOP;

  return (
    <div className={styles.chartBlock}>
      <h4>{label}</h4>
      <svg
        aria-label={`Histórico continuo de ${label.toLowerCase()}. Pase el puntero para consultar una muestra.`}
        className={styles.chart}
        onPointerLeave={() => setHoveredIndex(null)}
        onPointerMove={handlePointerMove}
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      >
        <rect className={styles.hitArea} height={plotHeight} width={plotWidth} x={LEFT} y={TOP} />
        <line className={styles.grid} x1={LEFT} x2={WIDTH - RIGHT} y1={TOP} y2={TOP} />
        <line className={styles.grid} x1={LEFT} x2={WIDTH - RIGHT} y1={TOP + plotHeight / 2} y2={TOP + plotHeight / 2} />
        <line className={styles.grid} x1={LEFT} x2={WIDTH - RIGHT} y1={TOP + plotHeight} y2={TOP + plotHeight} />
        <text className={styles.axisLabel} textAnchor="end" x={LEFT - 9} y={TOP + 5}>{Math.round(ceiling)}</text>
        <text className={styles.axisLabel} textAnchor="end" x={LEFT - 9} y={TOP + plotHeight + 5}>{Math.round(floor)}</text>
        <polyline className={`${styles.levelLine} ${colorClass}`} points={polylinePoints} />
        {hoveredPoint && hoveredCoordinate && (
          <g className={styles.hoverDetail}>
            <line className={styles.hoverGuide} x1={hoveredCoordinate.x} x2={hoveredCoordinate.x} y1={TOP} y2={TOP + plotHeight} />
            <circle className={`${styles.hoverPoint} ${colorClass}`} cx={hoveredCoordinate.x} cy={hoveredCoordinate.y} r="5" />
            <rect className={styles.tooltip} height={TOOLTIP_HEIGHT} rx="7" width={TOOLTIP_WIDTH} x={tooltipX} y={tooltipY} />
            <text className={styles.tooltipText} x={tooltipX + 12} y={tooltipY + 20}>
              <tspan>{timestampFormatter.format(new Date(hoveredPoint.timestamp_real * 1_000))}</tspan>
              <tspan className={styles.tooltipValue} x={tooltipX + 12} dy="20">Nivel: {value(hoveredPoint).toLocaleString("es-AR", { maximumFractionDigits: 2 })}</tspan>
            </text>
          </g>
        )}
        <text className={styles.axisLabel} x={LEFT} y={HEIGHT - 9}>Día simulado −{simulatedDays.toFixed(1)}</text>
        <text className={styles.axisLabel} textAnchor="end" x={WIDTH - RIGHT} y={HEIGHT - 9}>Ahora</text>
      </svg>
    </div>
  );
}

export interface LevelHistoryChartProps {
  chamberCeiling: number;
  chamberFloor: number;
  history: LevelHistory | null;
  reserveCeiling: number;
  reserveFloor: number;
}

export function LevelHistoryChart({
  chamberCeiling,
  chamberFloor,
  history,
  reserveCeiling,
  reserveFloor,
}: LevelHistoryChartProps) {
  const points = history?.points ?? [];
  return (
    <section className={styles.history}>
      <div className={styles.heading}>
        <div>
          <h3>Histórico de niveles</h3>
          <p>Líneas continuas con una muestra cada 30 segundos reales.</p>
        </div>
        <span>{history?.stored_points ?? 0} muestras · {history?.retention_simulated_days ?? 180} días simulados</span>
      </div>
      <div className={styles.gridCharts}>
        <LineChart
          ceiling={chamberCeiling}
          colorClass={styles.chamberLine!}
          floor={chamberFloor}
          label="Nivel de cámara"
          points={points}
          value={(point) => point.chamber_level}
        />
        <LineChart
          ceiling={reserveCeiling}
          colorClass={styles.reserveLine!}
          floor={reserveFloor}
          label="Nivel de reserva"
          points={points}
          value={(point) => point.reserve_level}
        />
      </div>
    </section>
  );
}
