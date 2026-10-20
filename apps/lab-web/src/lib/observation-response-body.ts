/** Keep browser observation bodies bounded before allocating the decoded text. */
export class InvalidObservationBody extends Error {
  constructor() { super('INVALID_RECORD'); }
}

/** Request disposal without waiting for an unused provider body or its cancel promise. */
export function discardObservationBody(response: Response): void {
  try { void response.body?.cancel().catch(() => undefined); } catch { /* No provider detail escapes. */ }
}

export async function boundedObservationText(response: Response, maximumBytes: number): Promise<string> {
  if (!Number.isSafeInteger(maximumBytes) || maximumBytes < 1) throw new InvalidObservationBody();
  if (!response.body) return '';
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const item = await reader.read();
      if (item.done) break;
      size += item.value.byteLength;
      if (size > maximumBytes) {
        // Cancellation is requested immediately. An uncooperative cancel promise
        // must not prevent the card from retaining its last validated record.
        try { void reader.cancel().catch(() => undefined); } catch { /* Fixed failure below. */ }
        throw new InvalidObservationBody();
      }
      chunks.push(item.value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let cursor = 0;
  for (const chunk of chunks) { bytes.set(chunk, cursor); cursor += chunk.byteLength; }
  try { return new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes); }
  catch { throw new InvalidObservationBody(); }
}
