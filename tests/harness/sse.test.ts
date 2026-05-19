import { describe, it, expect } from 'vitest';
import { collectSSEEvents, parseSSEStream } from '../../src/client/sse.js';
import { reportStep } from './test-output.js';

function responseFromText(text: string) {
  return new Response(new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(text)); c.close(); } }));
}

describe('SSE Parser', () => {
  it('parses single event', async () => {
    reportStep('SSE single event', 'collect one processing event from a valid SSE frame');
    const evts = await collectSSEEvents(responseFromText('data: {"event_type":"processing","data":null,"seq":1}\n\n'), { timeoutMs: 5000 });
    reportStep('SSE single event', 'observed events', evts.map((event) => event.event_type));
    expect(evts).toHaveLength(1);
    expect(evts[0].event_type).toBe('processing');
  });

  it('parses multiple events', async () => {
    reportStep('SSE multiple events', 'collect processing and turn_complete frames');
    const evts = await collectSSEEvents(responseFromText('data: {"event_type":"processing","data":null}\n\ndata: {"event_type":"turn_complete","data":{"final_response":"Hi"}}\n\n'), { timeoutMs: 5000 });
    reportStep('SSE multiple events', 'observed final response', evts[1].data?.['final_response']);
    expect(evts).toHaveLength(2);
    expect(evts[1].data?.['final_response']).toBe('Hi');
  });

  it('parses CRLF and multi-line data events', async () => {
    const stream = [
      ': backend heartbeat\r\n',
      'data: {"event_type":"assistant_message",\r\n',
      'data: "data":{"content":"hello"},\r\n',
      'data: "seq":7}\r\n',
      '\r\n',
    ].join('');

    reportStep('SSE multiline event', 'collect a CRLF stream with repeated data fields');
    const evts = await collectSSEEvents(responseFromText(stream), { timeoutMs: 5000 });
    reportStep('SSE multiline event', 'observed parsed event', evts[0]);

    expect(evts).toHaveLength(1);
    expect(evts[0].event_type).toBe('assistant_message');
    expect(evts[0].seq).toBe(7);
    expect(evts[0].data?.['content']).toBe('hello');
  });

  it('stops after stopAfter', async () => {
    reportStep('SSE stopAfter', 'collect until turn_complete and ignore later frames');
    const evts = await collectSSEEvents(responseFromText('data: {"event_type":"processing","data":null}\n\ndata: {"event_type":"turn_complete","data":{}}\n\ndata: {"event_type":"extra","data":{}}\n\n'), { stopAfter: 'turn_complete', timeoutMs: 5000 });
    reportStep('SSE stopAfter', 'observed events', evts.map((event) => event.event_type));
    expect(evts).toHaveLength(2);
  });

  it('skips comments and invalid JSON', async () => {
    reportStep('SSE invalid frame handling', 'collect valid frames while skipping comments and invalid JSON');
    const evts = await collectSSEEvents(responseFromText(': comment\ndata: {"event_type":"ok","data":{}}\n\ndata: bad\n\n'), { timeoutMs: 5000 });
    reportStep('SSE invalid frame handling', 'observed events', evts.map((event) => event.event_type));
    expect(evts).toHaveLength(1);
    expect(evts[0].event_type).toBe('ok');
  });

  it('handles [DONE]', async () => {
    reportStep('SSE done frame', 'collect data before [DONE]');
    const evts = await collectSSEEvents(responseFromText('data: {"event_type":"ok","data":null}\n\ndata: [DONE]\n\n'), { timeoutMs: 5000 });
    reportStep('SSE done frame', 'observed events', evts.map((event) => event.event_type));
    expect(evts).toHaveLength(1);
  });

  it('throws when response body is missing', async () => {
    reportStep('SSE missing body', 'attempt to parse a response with no body');
    const iterator = parseSSEStream(new Response(null));
    await expect(iterator.next()).rejects.toThrow('SSE response has no body');
    reportStep('SSE missing body', 'observed expected parser error');
  });
});
