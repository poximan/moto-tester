import { Button, Card } from "@servicoop/frontend-foundation";
import { useEffect, useRef, useState } from "react";

import type { TrasvaseApiClient } from "../TrasvaseApiClient";
import type { LogIndex } from "../TrasvaseModels";
import styles from "./LogsPanel.module.css";

export interface LogsPanelProps { client: TrasvaseApiClient; }

export function LogsPanel({ client }: LogsPanelProps) {
  const [logs, setLogs] = useState<LogIndex | null>(null);
  const [indexError, setIndexError] = useState<string | null>(null);
  const [indexRevision, setIndexRevision] = useState(0);
  const [selected, setSelected] = useState("");
  const [lineCount, setLineCount] = useState(300);
  const [content, setContent] = useState("Sin logs cargados.");
  const [meta, setMeta] = useState("");
  const outputRef = useRef<HTMLPreElement>(null);

  const loadLog = async (name = selected, lines = lineCount) => {
    try {
      const result = await client.getLog(name, lines);
      setContent(result.lines.length > 0 ? result.lines.join("\n") : `Sin líneas para ${result.filename}`);
      setMeta(`${result.filename} · ${result.exists ? `${result.lines.length} líneas` : "no existe"}`);
    } catch (error) {
      setMeta(error instanceof Error ? error.message : "No se pudo leer el log");
    }
  };
  const loadDiagnostics = async () => {
    try {
      setContent(JSON.stringify(await client.getDiagnostics(), null, 2));
      setMeta("Diagnóstico");
    } catch (error) {
      setMeta(error instanceof Error ? error.message : "No se pudo leer el diagnóstico");
    }
  };
  useEffect(() => {
    const controller = new AbortController();
    setIndexError(null);
    client.getLogs(controller.signal).then((index) => {
      if (controller.signal.aborted) return;
      setLogs(index);
      setSelected(index.files[0]?.name ?? "");
      setMeta(`${index.files.length} log(s) · ${index.log_dir}`);
    }).catch((error) => {
      if (controller.signal.aborted) return;
      setIndexError(error instanceof Error ? error.message : "No se pudo cargar el índice de logs");
    });
    return () => controller.abort();
  }, [client, indexRevision]);
  useEffect(() => {
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [content]);

  return (
    <Card>
      <div className={styles.heading}><div><h2>Diagnóstico y logs</h2><p>Consulta controlada de conexión, lecturas y errores recientes.</p></div><Button onClick={() => void loadDiagnostics()} variant="secondary">Ver diagnóstico</Button></div>
      {indexError && <div role="alert">{indexError} <Button onClick={() => setIndexRevision((revision) => revision + 1)} variant="ghost">Reintentar logs</Button></div>}
      {!logs && !indexError && <p>Cargando índice de logs…</p>}
      {logs && (
      <div className={styles.toolbar}>
        <label>Archivo <select onChange={(event) => {
          const name = event.target.value;
          setSelected(name);
          void loadLog(name, lineCount);
        }} value={selected}>{logs.files.map((file) => <option key={file.name} value={file.name}>{file.filename} · {file.source === "local" ? `${file.size_bytes} bytes` : "remoto"}</option>)}</select></label>
        <label>Últimas líneas <input max={5_000} min={20} onChange={(event) => setLineCount(event.target.valueAsNumber)} step={50} type="number" value={lineCount} /></label>
        <Button disabled={!selected} onClick={() => void loadLog()} variant="ghost">Cargar archivo</Button>
      </div>
      )}
      <p role="status">{meta}</p>
      <pre className={styles.output} ref={outputRef}>{content}</pre>
    </Card>
  );
}
