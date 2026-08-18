import { Button, Card } from "@servicoop/frontend-foundation";

import type { TrasvaseApiClient } from "../TrasvaseApiClient";
import { TrasvasePresenter } from "../TrasvasePresenter";
import type { EmarMode, PumpSnapshot, SignalValue } from "../TrasvaseModels";
import { FixedPositionSelector } from "./FixedPositionSelector";
import styles from "./PumpCard.module.css";

export interface PumpCardProps {
  client: TrasvaseApiClient;
  connected: boolean;
  execute: (operation: () => Promise<unknown>) => Promise<boolean>;
  presenter: TrasvasePresenter;
  pump: PumpSnapshot;
  rtuSelection: SignalValue | undefined;
}

const emarModes: ReadonlyArray<{ label: string; value: EmarMode }> = [
  { label: "Deshabilitado", value: "disabled" },
  { label: "Automático", value: "automatic" },
  { label: "Forzar", value: "forced" },
];

export function PumpCard({ client, connected, execute, presenter, pump, rtuSelection }: PumpCardProps) {
  const visual = presenter.pumpVisual(pump, connected);
  const rtu = presenter.signalBoolean(rtuSelection?.value == null ? pump.rtu : rtuSelection);
  const automatic = presenter.signalBoolean(pump.cmd_aut);

  const command = (values: { aut?: boolean; mr?: boolean }) => execute(() => client.sendPump(pump.id, values));
  const indicator = (label: string, active: boolean, danger = false) => (
    <span><i className={active ? danger ? styles.danger : styles.on : styles.off} />{label}</span>
  );

  return (
    <Card className={styles.card}>
      <div className={styles.heading}><h3>Bomba {pump.id}</h3></div>
      <img alt={`Bomba ${pump.id}: ${visual.label}`} className={styles.image} src={`assets/pump_${visual.image}.png`} />
      <strong className={styles.hours}>{presenter.signalText(pump.hours)} h</strong>
      <div className={styles.indicators}>
        {indicator("RTU", rtu)}{indicator("Automático", presenter.signalBoolean(pump.aut))}
        {indicator("Salud", presenter.signalBoolean(pump.ok))}{indicator("EMar", presenter.signalBoolean(pump.running))}
        {indicator("Falla", presenter.signalBoolean(pump.fault), true)}
      </div>
      <div className={styles.options}>
        <fieldset className={styles.emarModes}>
          <legend>generar EMar</legend>
          <div className={styles.emarOptions}>
            {emarModes.map((option) => (
              <label key={option.value}>
                <input
                  checked={pump.emar_mode === option.value}
                  name={`pump-${pump.id}-emar-mode`}
                  onChange={() => void execute(() => client.setEmarMode(pump.id, option.value))}
                  type="radio"
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
        <FixedPositionSelector onChange={(nextRtu) => void execute(() => client.inject(`yB${pump.id}RTU`, nextRtu))} rtu={rtu} />
      </div>
      <div className={styles.commands}>
        <Button className={styles.modeCommand} onClick={() => void command({ aut: !automatic })} variant="secondary">{automatic ? "Auto" : "Man"}</Button>
        <div className={styles.runCommands}>
          <Button onClick={() => void command({ mr: true })}>Marcha</Button>
          <Button onClick={() => void command({ mr: false })} variant="secondary">Parada</Button>
        </div>
      </div>
    </Card>
  );
}
