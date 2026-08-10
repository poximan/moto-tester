import { Button } from "@servicoop/frontend-foundation";
import { useEffect, useState } from "react";

import styles from "./SetpointEditor.module.css";

export interface SetpointEditorProps {
  onApply: (value: number) => Promise<void>;
  tag: string;
  value: number | null;
}

export function SetpointEditor({ onApply, tag, value }: SetpointEditorProps) {
  const [draft, setDraft] = useState(value === null ? "" : String(value));
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!editing) setDraft(value === null ? "" : String(value));
  }, [editing, value]);

  const apply = () => {
    const parsed = Number(draft);
    if (!Number.isInteger(parsed)) return;
    void onApply(parsed).then(() => setEditing(false));
  };

  return (
    <span className={styles.editor}>
      <input
        aria-label={`Consigna ${tag}`}
        onBlur={(event) => {
          if (!event.currentTarget.parentElement?.contains(event.relatedTarget as Node | null)) setEditing(false);
        }}
        onChange={(event) => setDraft(event.target.value)}
        onFocus={() => setEditing(true)}
        onKeyDown={(event) => { if (event.key === "Enter") apply(); }}
        step={1}
        type="number"
        value={draft}
      />
      <Button onClick={apply} variant="ghost">Aplicar</Button>
    </span>
  );
}
