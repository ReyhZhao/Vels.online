import { describe, it, expect } from 'vitest';
import { parseSSEChunk } from './parseSSE';

function freshBuffer() {
  return { remainder: '' };
}

describe('parseSSEChunk', () => {
  it('parses a single complete event', () => {
    const buf = freshBuffer();
    const events = parseSSEChunk('event: phase\ndata: {"phase":"research"}\n\n', buf);
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ event: 'phase', data: { phase: 'research' } });
    expect(buf.remainder).toBe('');
  });

  it('parses multiple events in one chunk', () => {
    const buf = freshBuffer();
    const chunk =
      'event: phase\ndata: {"phase":"research"}\n\n' +
      'event: tool\ndata: {"tool":"web_search","summary":"ok"}\n\n';
    const events = parseSSEChunk(chunk, buf);
    expect(events).toHaveLength(2);
    expect(events[0].event).toBe('phase');
    expect(events[1].event).toBe('tool');
  });

  it('carries a partial event over a chunk boundary', () => {
    const buf = freshBuffer();
    // First chunk: only half of the event
    const eventsFirst = parseSSEChunk('event: tool\ndata: {"tool":"w', buf);
    expect(eventsFirst).toHaveLength(0);
    expect(buf.remainder).toBe('event: tool\ndata: {"tool":"w');

    // Second chunk: rest of the event + blank line
    const eventsSecond = parseSSEChunk('eb_search"}\n\n', buf);
    expect(eventsSecond).toHaveLength(1);
    expect(eventsSecond[0].event).toBe('tool');
    expect(eventsSecond[0].data.tool).toBe('web_search');
    expect(buf.remainder).toBe('');
  });

  it('handles an event split with the blank separator across chunks', () => {
    const buf = freshBuffer();
    // First chunk ends just before the double newline
    parseSSEChunk('event: done\ndata: {}', buf);
    // Second chunk is just the separator
    const events = parseSSEChunk('\n\n', buf);
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('done');
  });

  it('accumulates remainder across three chunks', () => {
    const buf = freshBuffer();
    parseSSEChunk('event: result\n', buf);
    parseSSEChunk('data: {"assistant_reply":"hi"}\n', buf);
    const events = parseSSEChunk('\n', buf);
    expect(events).toHaveLength(1);
    expect(events[0].data.assistant_reply).toBe('hi');
  });

  it('ignores records without a recognized event type', () => {
    const buf = freshBuffer();
    // a record with no event: line
    const events = parseSSEChunk('data: {"foo":"bar"}\n\n', buf);
    expect(events).toHaveLength(0);
  });

  it('ignores records with unparseable JSON', () => {
    const buf = freshBuffer();
    const events = parseSSEChunk('event: tool\ndata: {invalid json}\n\n', buf);
    expect(events).toHaveLength(0);
  });

  it('handles an empty chunk without changing buffer', () => {
    const buf = freshBuffer();
    buf.remainder = 'event: phase\n';
    const events = parseSSEChunk('', buf);
    expect(events).toHaveLength(0);
    expect(buf.remainder).toBe('event: phase\n');
  });

  it('parses a full normal sequence ending with done', () => {
    const buf = freshBuffer();
    const sequence =
      'event: phase\ndata: {"phase":"research"}\n\n' +
      'event: tool\ndata: {"tool":"web_search","count":2}\n\n' +
      'event: phase\ndata: {"phase":"synthesis"}\n\n' +
      'event: result\ndata: {"assistant_reply":"answer","proposed_actions":[],"warnings":[]}\n\n' +
      'event: done\ndata: {}\n\n';
    const events = parseSSEChunk(sequence, buf);
    const types = events.map(e => e.event);
    expect(types).toEqual(['phase', 'tool', 'phase', 'result', 'done']);
    expect(types[types.length - 1]).toBe('done');
    expect(types[types.length - 2]).toBe('result');
  });

  it('parses an error sequence ending with done', () => {
    const buf = freshBuffer();
    const sequence =
      'event: error\ndata: {"detail":"provider blew up"}\n\n' +
      'event: done\ndata: {}\n\n';
    const events = parseSSEChunk(sequence, buf);
    const types = events.map(e => e.event);
    expect(types).toEqual(['error', 'done']);
    expect(events[0].data.detail).toBe('provider blew up');
  });
});
