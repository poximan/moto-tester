import { useCallback, useEffect, useMemo, useState } from "react";

import { TrasvaseApiClient } from "./TrasvaseApiClient";
import type { EmulatorState, LogIndex, RuntimeSnapshot, TesterConfig } from "./TrasvaseModels";
import { TrasvaseStreamClient, type StreamState } from "./TrasvaseStreamClient";

export interface TrasvaseDataState {
  client: TrasvaseApiClient;
  config: TesterConfig | null;
  emulator: EmulatorState | null;
  error: string | null;
  execute: (operation: () => Promise<unknown>) => Promise<boolean>;
  loading: boolean;
  logs: LogIndex | null;
  refreshSnapshot: () => Promise<void>;
  snapshot: RuntimeSnapshot | null;
  streamState: StreamState;
}

export function useTrasvaseData(): TrasvaseDataState {
  const client = useMemo(() => new TrasvaseApiClient(new URL("./", document.baseURI)), []);
  const stream = useMemo(() => new TrasvaseStreamClient(client.streamUrl), [client]);
  const [config, setConfig] = useState<TesterConfig | null>(null);
  const [snapshot, setSnapshot] = useState<RuntimeSnapshot | null>(null);
  const [emulator, setEmulator] = useState<EmulatorState | null>(null);
  const [logs, setLogs] = useState<LogIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [streamState, setStreamState] = useState<StreamState>("connecting");

  const refreshSnapshot = useCallback(async () => {
    setSnapshot(await client.getSnapshot());
  }, [client]);

  const execute = useCallback(async (operation: () => Promise<unknown>): Promise<boolean> => {
    try {
      await operation();
      await refreshSnapshot();
      setError(null);
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Operación rechazada por el servicio");
      return false;
    }
  }, [refreshSnapshot]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    Promise.all([
      client.getConfig(controller.signal),
      client.getSnapshot(controller.signal),
      client.getEmulator(controller.signal),
      client.getLogs(controller.signal),
    ]).then(([nextConfig, nextSnapshot, nextEmulator, nextLogs]) => {
      if (!active) return;
      setConfig(nextConfig);
      setSnapshot(nextSnapshot);
      setEmulator(nextEmulator);
      setLogs(nextLogs);
      setError(null);
      setLoading(false);
      stream.start((payload) => {
        setSnapshot(payload.snapshot);
        setEmulator(payload.emulator);
        setError(null);
      }, setStreamState, (streamError) => setError(streamError.message));
    }).catch((caught) => {
      if (!active) return;
      setError(caught instanceof Error ? caught.message : "No se pudo iniciar Trasvase Tester");
      setLoading(false);
    });
    return () => {
      active = false;
      controller.abort();
      stream.stop();
    };
  }, [client, stream]);

  return { client, config, emulator, error, execute, loading, logs, refreshSnapshot, snapshot, streamState };
}
