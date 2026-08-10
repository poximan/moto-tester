import type { TrasvaseApiClient } from "../TrasvaseApiClient";
import { TrasvasePresenter } from "../TrasvasePresenter";
import type { EmulatorState, RuntimeSnapshot } from "../TrasvaseModels";
import { PumpCard } from "./PumpCard";
import styles from "./PumpGrid.module.css";

export interface PumpGridProps {
  client: TrasvaseApiClient;
  emulator: EmulatorState | null;
  execute: (operation: () => Promise<unknown>) => Promise<boolean>;
  presenter: TrasvasePresenter;
  snapshot: RuntimeSnapshot;
}

export function PumpGrid({ client, emulator, execute, presenter, snapshot }: PumpGridProps) {
  return (
    <section>
      <div className={styles.heading}><h2>Bombas 4+1</h2><p>Estado, selectora fija Tablero/RTU, generación EMar y comandos operativos.</p></div>
      <div className={styles.grid}>
        {snapshot.groups.pumps.map((pump) => (
          <PumpCard
            client={client}
            connected={snapshot.connection.connected}
            generateEmar={emulator?.generate_emar?.[String(pump.id)] ?? false}
            execute={execute}
            key={pump.id}
            presenter={presenter}
            pump={pump}
            rtuSelection={snapshot.values[`yB${pump.id}RTU`]}
          />
        ))}
      </div>
    </section>
  );
}
