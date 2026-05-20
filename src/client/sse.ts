import type { SSEEvent } from './types.js';

export async function* parseSSEStream(response: Response): AsyncGenerator<SSEEvent> {
  if (!response.body) {
    throw new Error('SSE response has no body');
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value.replace(/\r\n/g, '\n');

      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';
      for (const part of parts) {
        const event = parseBlock(part.trim());
        if (event) yield event;
      }
    }

    if (buffer.trim()) {
      const event = parseBlock(buffer.trim());
      if (event) yield event;
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // Best-effort cleanup when the consumer stops early.
    }
    reader.releaseLock();
  }
}

export async function collectSSEEvents(
  response: Response,
  opts: { stopAfter?: string; maxEvents?: number; timeoutMs?: number } = {},
): Promise<SSEEvent[]> {
  const events: SSEEvent[] = [];
  const maxEvents = opts.maxEvents ?? 500;
  const timeoutMs = opts.timeoutMs ?? 120_000;

  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(`SSE timeout after ${timeoutMs}ms`)), timeoutMs);
  });

  const collectPromise = (async () => {
    for await (const event of parseSSEStream(response)) {
      events.push(event);
      if (opts.stopAfter && event.event_type === opts.stopAfter) {
        break;
      }
      if (events.length >= maxEvents) {
        break;
      }
    }
  })();

  try {
    await Promise.race([collectPromise, timeoutPromise]);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!message.startsWith('SSE timeout')) {
      throw error;
    }
    await response.body?.cancel().catch(() => undefined);
    if (events.length === 0) {
      throw error;
    }
  } finally {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId);
    }
  }

  return events;
}

function parseBlock(block: string): SSEEvent | null {
  if (!block) {
    return null;
  }

  const dataLines: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) {
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  const data = dataLines.join('\n').trim();
  if (!data || data === '[DONE]') {
    return null;
  }

  try {
    const payload = JSON.parse(data) as { event_type?: string; data?: Record<string, unknown> | null; seq?: number | null };
    return {
      event_type: payload.event_type ?? 'unknown',
      data: payload.data ?? (payload as Record<string, unknown>),
      seq: payload.seq ?? null,
    };
  } catch {
    return null;
  }
}
