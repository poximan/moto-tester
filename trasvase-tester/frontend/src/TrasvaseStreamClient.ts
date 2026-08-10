import { TrasvaseContractParser } from "./TrasvaseContractParser";
import type { StreamPayload } from "./TrasvaseModels";

export type StreamState = "connecting" | "connected" | "reconnecting" | "stopped";

export class TrasvaseStreamClient {
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private running = false;

  public constructor(
    private readonly url: URL,
    private readonly parser = new TrasvaseContractParser(),
    private readonly reconnectMilliseconds = 1_500,
  ) {}

  public start(
    onPayload: (payload: StreamPayload) => void,
    onState: (state: StreamState) => void,
    onError: (error: Error) => void,
  ): void {
    if (this.running) return;
    this.running = true;
    this.connect(onPayload, onState, onError, "connecting");
  }

  public stop(onState?: (state: StreamState) => void): void {
    this.running = false;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    onState?.("stopped");
  }

  private connect(
    onPayload: (payload: StreamPayload) => void,
    onState: (state: StreamState) => void,
    onError: (error: Error) => void,
    state: StreamState,
  ): void {
    if (!this.running) return;
    onState(state);
    const socket = new WebSocket(this.url);
    this.socket = socket;
    socket.addEventListener("open", () => onState("connected"));
    socket.addEventListener("message", (event) => {
      try {
        onPayload(this.parser.parseStream(JSON.parse(String(event.data))));
      } catch (error) {
        const contractError = error instanceof Error ? error : new Error("Contrato WebSocket inválido");
        onError(contractError);
        socket.close(1003, contractError.message.slice(0, 120));
      }
    });
    socket.addEventListener("error", () => socket.close());
    socket.addEventListener("close", () => {
      if (!this.running || this.socket !== socket) return;
      onState("reconnecting");
      this.reconnectTimer = window.setTimeout(
        () => this.connect(onPayload, onState, onError, "reconnecting"),
        this.reconnectMilliseconds,
      );
    });
  }
}
