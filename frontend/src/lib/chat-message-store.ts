/**
 * Lightweight localStorage persistence for UIMessage arrays,
 * keyed by session ID.
 *
 * Uses the same storage namespace (`hf-agent-messages`) that the
 * old Zustand-based store used, so existing data is compatible.
 */
import type { UIMessage } from 'ai';
import { logger } from '@/utils/logger';
import { createJsonMapStore } from './json-map-store';

const STORAGE_KEY = 'hf-agent-messages';
const MAX_SESSIONS = 50;

type MessagesMap = Record<string, UIMessage[]>;

const store = createJsonMapStore<UIMessage[]>(STORAGE_KEY, (e) => {
  logger.warn('Failed to persist messages:', e);
});

function readAll(): MessagesMap {
  const map = store.readAll();
  if ('messagesBySession' in map) {
    const legacy = (map as { messagesBySession?: MessagesMap }).messagesBySession;
    if (legacy && typeof legacy === 'object') {
      store.writeAll(legacy);
      return legacy;
    }
  }
  return map;
}

export function loadMessages(sessionId: string): UIMessage[] {
  const map = readAll();
  const messages = map[sessionId] ?? [];
  return messages;
}

export function saveMessages(sessionId: string, messages: UIMessage[]): void {
  const map = readAll();
  map[sessionId] = messages;

  // Evict oldest sessions if we exceed the cap
  const keys = Object.keys(map);
  if (keys.length > MAX_SESSIONS) {
    const toRemove = keys.slice(0, keys.length - MAX_SESSIONS);
    for (const k of toRemove) delete map[k];
  }

  store.writeAll(map);
}

export function deleteMessages(sessionId: string): void {
  const map = readAll();
  if (!(sessionId in map)) return;
  delete map[sessionId];
  store.writeAll(map);
}

export function moveMessages(fromId: string, toId: string): void {
  const map = readAll();
  if (!map[fromId]) return;
  map[toId] = map[fromId];
  delete map[fromId];
  store.writeAll(map);
}
