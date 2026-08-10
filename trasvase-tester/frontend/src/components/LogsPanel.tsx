import { Button, Card } from "@servicoop/frontend-foundation";
import { useEffect, useState } from "react";

import type { TrasvaseApiClient } from "../TrasvaseApiClient";
import type { LogIndex } from "../TrasvaseModels";
import styles from "./LogsPanel.module.css";

export interface LogsPanelProps { client: TrasvaseApiClient; logs: LogIndex; }

export function LogsPanel({ client, logs }: LogsPanelProps) {
  const [selected, setSelected] = useState(logs.files[0]?.name ?? "trasvase-tester");
  const [lineCount, setLineCount] = useState(300);
  const [content, setContent] = useState("Sin logs cargados.");
  const [meta, setMeta] = useState(`${logs.files.length} log(s) · ${logs.log_dir}`);

  const loadLog = async () => {
    try {
      const result = await client.getLog(selected, lineCount);
      setContent(result.lines.length > 0 ? result.lines.join("\n") : `Sin líneas para ${result.filename}`);
      setMeta(`${result.filename} · ${result.exists ? `${result.lines.length} líneas` : "no existe"}`);
    } catch (error) {
      setMeta(error instanceof Error ? error.message : "No se pudo leer el log");
    }
  };
  const loadDiagnostics = async () => {
    try {
      setContent(JSON.stringify(await client.getDiagnostics(), null, 2));
      setMeta(`Diagnóstico · ${logs.log_dir}`);
    } catch (error) {
      setMeta(error instanceof Error ? error.message : "No se pudo leer el diagnóstico");
    }
  };
  useEffect(() => { if (logs.files.length > 0) void loadLog(); }, []);

  return (
    <Card>
      <div className={styles.heading}><div><h2>Diagnóstico y logs</h2><p>Consulta controlada de conexión, lecturas y errores recientes.</p></div><Button onClick={() => void loadDiagnostics()} variant="secondary">Ver diagnóstico</Button></div>
      <div className={styles.toolbar}>
        <label>Archivo <select onChange={(event) => setSelected(event.target.value)} value={selected}>{logs.files.map((file) => <option key={file.name} value={file.name}>{file.filename} · {file.size_bytes} bytes</option>)}</select></label>
        <label>Últimas líneas <input max={5_000} min={20} onChange={(event) => setLineCount(event.target.valueAsNumber)} step={50} type="number" value={lineCount} /></label>
        <Button onClick={() => void loadLog()} variant="ghost">Recargar archivo</Button><span>{meta}</span>
      </div>
      <pre className={styles.output}>{content}</pre>
    </Card>
  );
}
