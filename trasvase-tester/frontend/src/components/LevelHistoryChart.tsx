import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";

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
const MINIMUM_DRAG_PIXELS = 8;

const timestampFormatter = new Intl.DateTimeFormat("es-AR", {
  dateStyle: "short",
  hour12: false,
  timeStyle: "medium",
  timeZone: "Etc/GMT+3",
});

const axisTimestampFormatter = new Intl.DateTimeFormat("es-AR", {
  day: "2-digit",
  hour: "2-digit",
  hour12: false,
  minute: "2-digit",
  month: "2-digit",
  timeZone: "Etc/GMT+3",
});

type InteractionMode = "pan" | "zoom";

interface TimeWindow {
  end: number;
  start: number;
}

interface DragState {
  initialWindow: TimeWindow;
  mode: InteractionMode;
  pointerId: number;
  startX: number;
}

interface DragSelection {
  currentX: number;
  startX: number;
}

function fitWindow(candidate: TimeWindow, bounds: TimeWindow, minimumSpan = 1): TimeWindow {
  const boundsSpan = Math.max(bounds.end - bounds.start, 1);
  const orderedStart = Math.min(candidate.start, candidate.end);
  const orderedEnd = Math.max(candidate.start, candidate.end);
  const span = Math.min(boundsSpan, Math.max(minimumSpan, orderedEnd - orderedStart));
  const center = (orderedStart + orderedEnd) / 2;
  let start = center - span / 2;
  let end = center + span / 2;

  if (start < bounds.start) {
    start = bounds.start;
    end = start + span;
  }
  if (end > bounds.end) {
    end = bounds.end;
    start = end - span;
  }
  return { end, start };
}

function isFullWindow(candidate: TimeWindow, bounds: TimeWindow): boolean {
  const tolerance = Math.max((bounds.end - bounds.start) / 10_000, 0.001);
  return candidate.start <= bounds.start + tolerance && candidate.end >= bounds.end - tolerance;
}

interface LineChartProps {
  ceiling: number;
  colorClass: string;
  floor: number;
  fullWindow: TimeWindow | null;
  interactionMode: InteractionMode;
  label: string;
  onResetView: () => void;
  onViewChange: (window: TimeWindow | null) => void;
  points: LevelHistoryPoint[];
  value: (point: LevelHistoryPoint) => number;
  viewWindow: TimeWindow | null;
}

function LineChart({
  ceiling,
  colorClass,
  floor,
  fullWindow,
  interactionMode,
  label,
  onResetView,
  onViewChange,
  points,
  value,
  viewWindow,
}: LineChartProps) {
  const clipId = `level-history-${useId().replace(/:/g, "")}`;
  const dragState = useRef<DragState | null>(null);
  const [dragSelection, setDragSelection] = useState<DragSelection | null>(null);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const first = points[0];
  const last = points.at(-1);

  if (!first || !last || !fullWindow || !viewWindow) {
    return <div className={styles.empty}>Todavía no hay muestras para {label.toLowerCase()}.</div>;
  }

  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const timeSpan = Math.max(viewWindow.end - viewWindow.start, 1);
  const fullSpan = Math.max(fullWindow.end - fullWindow.start, 1);
  const averageSampleInterval = points.length > 1
    ? Math.max((last.timestamp_real - first.timestamp_real) / (points.length - 1), 1)
    : 1;
  const minimumTimeSpan = Math.min(fullSpan, averageSampleInterval * 3);
  const valueSpan = Math.max(ceiling - floor, 1);
  const coordinates = points.map((point) => {
    const x = LEFT + ((point.timestamp_real - viewWindow.start) / timeSpan) * plotWidth;
    const normalized = Math.max(0, Math.min(1, (value(point) - floor) / valueSpan));
    const y = TOP + (1 - normalized) * plotHeight;
    return { x, y };
  });
  const polylinePoints = coordinates.map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const hoveredCandidate = hoveredIndex === null ? undefined : points[hoveredIndex];
  const hoveredPoint = hoveredCandidate
    && hoveredCandidate.timestamp_real >= viewWindow.start
    && hoveredCandidate.timestamp_real <= viewWindow.end
    ? hoveredCandidate
    : undefined;
  const hoveredCoordinate = hoveredPoint && hoveredIndex !== null ? coordinates[hoveredIndex] : undefined;

  const eventSvgX = (event: ReactPointerEvent<SVGSVGElement> | ReactWheelEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return ((event.clientX - rect.left) / rect.width) * WIDTH;
  };
  const plotX = (svgX: number) => Math.max(LEFT, Math.min(WIDTH - RIGHT, svgX));
  const timestampAt = (svgX: number, window: TimeWindow) => (
    window.start + ((plotX(svgX) - LEFT) / plotWidth) * (window.end - window.start)
  );
  const applyWindow = (candidate: TimeWindow) => {
    const fitted = fitWindow(candidate, fullWindow, minimumTimeSpan);
    onViewChange(isFullWindow(fitted, fullWindow) ? null : fitted);
  };
  const updateHoveredPoint = (svgX: number) => {
    if (svgX < LEFT || svgX > WIDTH - RIGHT) {
      setHoveredIndex(null);
      return;
    }
    const targetTimestamp = timestampAt(svgX, viewWindow);
    let nearestIndex: number | null = null;
    let nearestDistance = Number.POSITIVE_INFINITY;
    points.forEach((point, index) => {
      if (point.timestamp_real < viewWindow.start || point.timestamp_real > viewWindow.end) {
        return;
      }
      const distance = Math.abs(point.timestamp_real - targetTimestamp);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });
    setHoveredIndex(nearestIndex);
  };
  const finishDrag = (event: ReactPointerEvent<SVGSVGElement>, cancelled: boolean) => {
    const drag = dragState.current;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }
    if (!cancelled && drag.mode === "zoom") {
      const currentX = plotX(eventSvgX(event));
      if (Math.abs(currentX - drag.startX) >= MINIMUM_DRAG_PIXELS) {
        applyWindow({
          end: timestampAt(currentX, drag.initialWindow),
          start: timestampAt(drag.startX, drag.initialWindow),
        });
      }
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragState.current = null;
    setDragSelection(null);
  };

  const handlePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) {
      return;
    }
    const svgX = eventSvgX(event);
    if (svgX < LEFT || svgX > WIDTH - RIGHT) {
      return;
    }
    const startX = plotX(svgX);
    dragState.current = {
      initialWindow: viewWindow,
      mode: interactionMode,
      pointerId: event.pointerId,
      startX,
    };
    setDragSelection(interactionMode === "zoom" ? { currentX: startX, startX } : null);
    setHoveredIndex(null);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };
  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const svgX = eventSvgX(event);
    const drag = dragState.current;
    if (!drag || drag.pointerId !== event.pointerId) {
      updateHoveredPoint(svgX);
      return;
    }
    const currentX = plotX(svgX);
    if (drag.mode === "zoom") {
      setDragSelection({ currentX, startX: drag.startX });
      return;
    }
    const dragSpan = drag.initialWindow.end - drag.initialWindow.start;
    const timeOffset = ((drag.startX - currentX) / plotWidth) * dragSpan;
    applyWindow({
      end: drag.initialWindow.end + timeOffset,
      start: drag.initialWindow.start + timeOffset,
    });
  };
  const handleWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    const svgX = eventSvgX(event);
    if (svgX < LEFT || svgX > WIDTH - RIGHT) {
      return;
    }
    event.preventDefault();
    const anchorRatio = (plotX(svgX) - LEFT) / plotWidth;
    const limitedDelta = Math.max(-200, Math.min(200, event.deltaY));
    const factor = Math.exp(limitedDelta * 0.0015);
    const nextSpan = Math.max(minimumTimeSpan, Math.min(fullSpan, timeSpan * factor));
    const anchorTimestamp = viewWindow.start + anchorRatio * timeSpan;
    applyWindow({
      end: anchorTimestamp + (1 - anchorRatio) * nextSpan,
      start: anchorTimestamp - anchorRatio * nextSpan,
    });
    setHoveredIndex(null);
  };
  const tooltipX = hoveredCoordinate
    ? Math.max(LEFT, Math.min(WIDTH - RIGHT - TOOLTIP_WIDTH, hoveredCoordinate.x + 12))
    : LEFT;
  const tooltipY = hoveredCoordinate
    ? hoveredCoordinate.y > TOP + TOOLTIP_HEIGHT + 8
      ? hoveredCoordinate.y - TOOLTIP_HEIGHT - 8
      : hoveredCoordinate.y + 12
    : TOP;
  const selectionX = dragSelection ? Math.min(dragSelection.startX, dragSelection.currentX) : LEFT;
  const selectionWidth = dragSelection ? Math.abs(dragSelection.currentX - dragSelection.startX) : 0;
  const chartClassName = [
    styles.chart,
    interactionMode === "zoom" ? styles.zoomMode : styles.panMode,
    dragState.current ? styles.dragging : "",
  ].filter(Boolean).join(" ");

  return (
    <div className={styles.chartBlock}>
      <h4>{label}</h4>
      <svg
        aria-label={`Histórico continuo de ${label.toLowerCase()}. Arrastre para ${interactionMode === "zoom" ? "ampliar" : "desplazar"}, use la rueda para cambiar la escala y haga doble clic para restablecer.`}
        className={chartClassName}
        onDoubleClick={onResetView}
        onPointerCancel={(event) => finishDrag(event, true)}
        onPointerDown={handlePointerDown}
        onPointerLeave={() => {
          if (!dragState.current) {
            setHoveredIndex(null);
          }
        }}
        onPointerMove={handlePointerMove}
        onPointerUp={(event) => finishDrag(event, false)}
        onWheel={handleWheel}
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      >
        <defs>
          <clipPath id={clipId}>
            <rect height={plotHeight} width={plotWidth} x={LEFT} y={TOP} />
          </clipPath>
        </defs>
        <rect className={styles.hitArea} height={plotHeight} width={plotWidth} x={LEFT} y={TOP} />
        <line className={styles.grid} x1={LEFT} x2={WIDTH - RIGHT} y1={TOP} y2={TOP} />
        <line className={styles.grid} x1={LEFT} x2={WIDTH - RIGHT} y1={TOP + plotHeight / 2} y2={TOP + plotHeight / 2} />
        <line className={styles.grid} x1={LEFT} x2={WIDTH - RIGHT} y1={TOP + plotHeight} y2={TOP + plotHeight} />
        <text className={styles.axisLabel} textAnchor="end" x={LEFT - 9} y={TOP + 5}>{Math.round(ceiling)}</text>
        <text className={styles.axisLabel} textAnchor="end" x={LEFT - 9} y={TOP + plotHeight + 5}>{Math.round(floor)}</text>
        <g clipPath={`url(#${clipId})`}>
          <polyline className={`${styles.levelLine} ${colorClass}`} points={polylinePoints} />
          {hoveredPoint && hoveredCoordinate && (
            <g className={styles.hoverDetail}>
              <line className={styles.hoverGuide} x1={hoveredCoordinate.x} x2={hoveredCoordinate.x} y1={TOP} y2={TOP + plotHeight} />
              <circle className={`${styles.hoverPoint} ${colorClass}`} cx={hoveredCoordinate.x} cy={hoveredCoordinate.y} r="5" />
            </g>
          )}
          {dragSelection && (
            <rect className={styles.zoomSelection} height={plotHeight} width={selectionWidth} x={selectionX} y={TOP} />
          )}
        </g>
        {hoveredPoint && hoveredCoordinate && (
          <g className={styles.hoverDetail}>
            <rect className={styles.tooltip} height={TOOLTIP_HEIGHT} rx="7" width={TOOLTIP_WIDTH} x={tooltipX} y={tooltipY} />
            <text className={styles.tooltipText} x={tooltipX + 12} y={tooltipY + 20}>
              <tspan>{timestampFormatter.format(new Date(hoveredPoint.timestamp_real * 1_000))}</tspan>
              <tspan className={styles.tooltipValue} x={tooltipX + 12} dy="20">Nivel: {value(hoveredPoint).toLocaleString("es-AR", { maximumFractionDigits: 2 })}</tspan>
            </text>
          </g>
        )}
        <text className={styles.axisLabel} x={LEFT} y={HEIGHT - 9}>
          {axisTimestampFormatter.format(new Date(viewWindow.start * 1_000))}
        </text>
        <text className={styles.axisLabel} textAnchor="end" x={WIDTH - RIGHT} y={HEIGHT - 9}>
          {axisTimestampFormatter.format(new Date(viewWindow.end * 1_000))}
        </text>
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
  const firstTimestamp = points[0]?.timestamp_real;
  const lastTimestamp = points.at(-1)?.timestamp_real;
  const fullWindow = useMemo(
    () => firstTimestamp === undefined || lastTimestamp === undefined
      ? null
      : { end: Math.max(lastTimestamp, firstTimestamp + 1), start: firstTimestamp },
    [firstTimestamp, lastTimestamp],
  );
  const [interactionMode, setInteractionMode] = useState<InteractionMode>("zoom");
  const [selectedWindow, setSelectedWindow] = useState<TimeWindow | null>(null);

  useEffect(() => {
    setSelectedWindow((current) => {
      if (!current || !fullWindow) {
        return null;
      }
      const fitted = fitWindow(current, fullWindow);
      return isFullWindow(fitted, fullWindow) ? null : fitted;
    });
  }, [fullWindow]);

  const viewWindow = fullWindow
    ? selectedWindow
      ? fitWindow(selectedWindow, fullWindow)
      : fullWindow
    : null;
  const zoomFactor = fullWindow && viewWindow
    ? (fullWindow.end - fullWindow.start) / Math.max(viewWindow.end - viewWindow.start, 1)
    : 1;
  const resetView = () => setSelectedWindow(null);

  return (
    <section className={styles.history}>
      <div className={styles.heading}>
        <div>
          <h3>Histórico de niveles</h3>
          <p>Líneas continuas con una muestra cada 30 segundos reales.</p>
        </div>
        <span>{history?.stored_points ?? 0} muestras · {history?.retention_simulated_days ?? 180} días simulados</span>
      </div>
      <div className={styles.interactionBar}>
        <div aria-label="Modo de interacción del histórico" className={styles.modeControls} role="group">
          <button
            aria-pressed={interactionMode === "zoom"}
            className={`${styles.modeButton} ${interactionMode === "zoom" ? styles.modeButtonActive : ""}`}
            disabled={!fullWindow}
            onClick={() => setInteractionMode("zoom")}
            type="button"
          >
            Ampliar
          </button>
          <button
            aria-pressed={interactionMode === "pan"}
            className={`${styles.modeButton} ${interactionMode === "pan" ? styles.modeButtonActive : ""}`}
            disabled={!fullWindow}
            onClick={() => setInteractionMode("pan")}
            type="button"
          >
            Mover
          </button>
          <button
            className={styles.resetButton}
            disabled={!selectedWindow}
            onClick={resetView}
            type="button"
          >
            Restablecer
          </button>
        </div>
        <p className={styles.interactionHint}>
          {interactionMode === "zoom" ? "Arrastrá sobre cualquier gráfico para ampliar." : "Arrastrá cualquier gráfico para desplazar el período."}
          {" "}La rueda ajusta el zoom y el doble clic restablece ambos. · {zoomFactor > 1.005 ? `Zoom ×${zoomFactor.toFixed(1)}` : "Vista completa"}
        </p>
      </div>
      <div className={styles.gridCharts}>
        <LineChart
          ceiling={chamberCeiling}
          colorClass={styles.chamberLine!}
          floor={chamberFloor}
          fullWindow={fullWindow}
          interactionMode={interactionMode}
          label="Nivel de cámara"
          onResetView={resetView}
          onViewChange={setSelectedWindow}
          points={points}
          value={(point) => point.chamber_level}
          viewWindow={viewWindow}
        />
        <LineChart
          ceiling={reserveCeiling}
          colorClass={styles.reserveLine!}
          floor={reserveFloor}
          fullWindow={fullWindow}
          interactionMode={interactionMode}
          label="Nivel de reserva"
          onResetView={resetView}
          onViewChange={setSelectedWindow}
          points={points}
          value={(point) => point.reserve_level}
          viewWindow={viewWindow}
        />
      </div>
    </section>
  );
}
