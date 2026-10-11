/**
 * Incremental NDJSON reader shared by the audit conversation and reproduction UI.
 * A fetch chunk may split an event at any byte boundary; EOF can also arrive
 * without a trailing newline. The server's event format remains unchanged.
 */
export async function consumeNdjson(response, onEvent) {
  if (!response.body || typeof response.body.getReader !== "function") {
    throw new Error("Live event streaming is unavailable in this browser.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lineNumber = 0;

  function consumeLine(line) {
    if (!line.trim()) return;
    lineNumber += 1;
    let event;
    try {
      event = JSON.parse(line);
    } catch {
      throw new Error(`Malformed server event at line ${lineNumber}.`);
    }
    if (event === null || typeof event !== "object" || Array.isArray(event)) {
      throw new Error(`Unexpected server event at line ${lineNumber}.`);
    }
    onEvent(event);
  }

  function drainLines() {
    let newline;
    while ((newline = buffer.indexOf("\n")) !== -1) {
      consumeLine(buffer.slice(0, newline).replace(/\r$/, ""));
      buffer = buffer.slice(newline + 1);
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (!value) continue;
      buffer += decoder.decode(value, { stream: true });
      drainLines();
    }
    buffer += decoder.decode();
    drainLines();
    consumeLine(buffer);
  } finally {
    reader.releaseLock();
  }
}
