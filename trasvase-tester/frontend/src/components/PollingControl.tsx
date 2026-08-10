import { Button, StatusBadge } from "@servicoop/frontend-foundation";
import { useEffect, useState } from "react";

import type { PollingFunction } from "../TrasvaseModels";
import styles from "./PollingControl.module.css";

export interface PollingControlProps {
  control: PollingFunction;
  functionCode: string;
  onUpdate: (functionCode: string, values: { enabled?: boolean; sample_rate_ms?: number }) => Promise<void>;
}

export function PollingControl({ control, functionCode, onUpdate }: PollingControlProps) {
  const [sampleRate, setSampleRate] = useState(control.sample_rate_ms);
  const [busy, setBusy] = useState(false);
  useEffect(() => setSampleRate(control.sample_rate_ms), [control.sample_rate_ms]);

  const update = async (values: { enabled?: boolean; sample_rate_ms?: number }) => {
    setBusy(true);
    try {
      await onUpdate(functionCode, values);
    } finally {
      setBusy(false);
    }
  };

  const saveRate = () => {
    if (!Number.isInteger(sampleRate) || sampleRate < 250 || sampleRate > 3_600_000) return;
    void update({ sample_rate_ms: sampleRate });
  };

  return (
    <div className={styles.control}>
      <Button
        aria-pressed={control.enabled}
        disabled={busy}
        onClick={() => void update({ enabled: !control.enabled })}
        variant={control.enabled ? "primary" : "ghost"}
      >
        FC{Number(functionCode)}
      </Button>
      <label>
        cada
        <input
          aria-label={`Intervalo FC${Number(functionCode)}`}
          max={3_600_000}
          min={250}
          onBlur={saveRate}
          onChange={(event) => setSampleRate(event.target.valueAsNumber)}
          onKeyDown={(event) => { if (event.key === "Enter") saveRate(); }}
          step={250}
          type="number"
          value={sampleRate}
        />
        ms
      </label>
      <StatusBadge tone={control.last_error ? "danger" : control.enabled ? "success" : "neutral"}>
        {control.last_error ? "Error" : control.enabled ? "Activa" : "Pausada"}
      </StatusBadge>
    </div>
  );
}
