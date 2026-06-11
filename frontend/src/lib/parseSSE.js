/**
 * SSE (Server-Sent Events) parser for the Incident Assistant streaming endpoint (ADR-0014).
 *
 * Turns raw byte chunks (including events split across chunk boundaries) into a
 * sequence of parsed event objects: { event: string, data: object }.
 *
 * Usage: call parseSSEChunk(text, buffer) where buffer is a mutable object
 * { remainder: string } that carries partial lines across calls.
 * Returns an array of { event, data } objects parsed from this chunk.
 */

/**
 * Parse one or more complete SSE records out of a text chunk.
 * `buffer.remainder` holds any partial line left from the previous chunk.
 *
 * @param {string} text - raw decoded text chunk from the stream
 * @param {{ remainder: string }} buffer - mutable carry-over state
 * @returns {{ event: string, data: object }[]}
 */
export function parseSSEChunk(text, buffer) {
  const events = [];
  const combined = buffer.remainder + text;
  // SSE records are separated by a blank line (\n\n)
  const records = combined.split('\n\n');
  // The last element is either empty (if the chunk ended on a boundary)
  // or a partial record that must carry over to the next chunk.
  buffer.remainder = records.pop() ?? '';

  for (const record of records) {
    const parsed = _parseRecord(record);
    if (parsed) events.push(parsed);
  }
  return events;
}

function _parseRecord(record) {
  let eventType = null;
  let dataStr = null;
  for (const line of record.split('\n')) {
    if (line.startsWith('event: ')) {
      eventType = line.slice('event: '.length);
    } else if (line.startsWith('data: ')) {
      dataStr = line.slice('data: '.length);
    }
  }
  if (!eventType || dataStr === null) return null;
  try {
    return { event: eventType, data: JSON.parse(dataStr) };
  } catch {
    return null;
  }
}

/**
 * Read a fetch Response as a stream of SSE events, calling onEvent for each.
 * The returned promise resolves when the stream ends (done event or connection close).
 * Pass an AbortController's signal as fetchOptions.signal to cancel mid-stream.
 *
 * @param {string} url
 * @param {RequestInit} fetchOptions
 * @param {(event: { event: string, data: object }) => void} onEvent
 */
export async function streamSSE(url, fetchOptions, onEvent) {
  const response = await fetch(url, fetchOptions);
  if (!response.ok || !response.body) {
    throw new Error(`HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const buffer = { remainder: '' };
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      const events = parseSSEChunk(chunk, buffer);
      for (const event of events) {
        onEvent(event);
        if (event.event === 'done') return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
