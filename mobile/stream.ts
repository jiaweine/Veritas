/** Incremental stream transport for the native audit and replication clients. */
type ResponseReader = {
  read: () => Promise<{ value?: Uint8Array; done: boolean }>;
  cancel?: () => Promise<void>;
};

type NativeStreamBody = {
  getReader?: () => ResponseReader;
  cancel?: () => Promise<void>;
};

export async function consumeNdjson<Event extends object>(
  response: Response,
  onEvent: (event: Event) => void,
  requireStreaming = false,
): Promise<void> {
  const body = response.body as unknown as NativeStreamBody | null;
  if (!body?.getReader || typeof TextDecoder === "undefined") {
    if (requireStreaming) {
      try { await body?.cancel?.(); } catch {}
      throw new Error("Interactive approval requires streaming fetch support in this mobile runtime.");
    }
    const text = await response.text();
    for (const line of text.split("\n")) {
      if (line.trim()) onEvent(JSON.parse(line) as Event);
    }
    return;
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (!value) continue;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as Event);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) onEvent(JSON.parse(buffer) as Event);
}
