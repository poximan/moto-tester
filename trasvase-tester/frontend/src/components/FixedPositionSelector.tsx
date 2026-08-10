import styles from "./FixedPositionSelector.module.css";

export interface FixedPositionSelectorProps {
  disabled?: boolean;
  onChange: (rtu: boolean) => void;
  rtu: boolean;
}

export function FixedPositionSelector({ disabled = false, onChange, rtu }: FixedPositionSelectorProps) {
  const position = rtu ? "RTU" : "Tablero";
  return (
    <div className={styles.selector}>
      <span className={!rtu ? styles.boardActive : undefined}>Tablero</span>
      <button
        aria-label={`Selectora fija Tablero RTU. Posición actual: ${position}`}
        aria-pressed={rtu}
        className={`${styles.head} ${rtu ? styles.rtuPosition : styles.boardPosition}`}
        disabled={disabled}
        onClick={() => onChange(!rtu)}
        title={`Cambiar a ${rtu ? "Tablero" : "RTU"}`}
        type="button"
      >
        <span className={styles.bezel}>
          <span className={`${styles.handle} ${rtu ? styles.handleRtu : styles.handleBoard}`} />
        </span>
      </button>
      <span className={rtu ? styles.rtuActive : undefined}>RTU</span>
      <small>Cabezal plástico tipo XB5 · 2 posiciones fijas</small>
    </div>
  );
}
