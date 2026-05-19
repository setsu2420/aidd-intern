const STORAGE_PREFIX = 'hf-agent-last-event:';
const FLUSH_DELAY_MS = 150;

let flushTimer: ReturnType<typeof setTimeout> | null = null;
const cachedSeqs = new Map<string, number>();
const dirtySessions = new Set<string>();
let storageListenerInstalled = false;

function storageKey(sessionId: string): string {
  return `${STORAGE_PREFIX}${sessionId}`;
}

function flushDirty(): void {
  const storage =
    typeof globalThis.localStorage === 'undefined' ? null : globalThis.localStorage;
  if (!storage) {
    dirtySessions.clear();
    return;
  }

  for (const sessionId of dirtySessions) {
    const seq = cachedSeqs.get(sessionId);
    if (seq == null) continue;
    try {
      storage.setItem(storageKey(sessionId), String(seq));
    } catch {
      // Best-effort cache. A later flush may still succeed.
    }
  }
  dirtySessions.clear();
}

function installListeners(): void {
  if (storageListenerInstalled || typeof window === 'undefined') return;

  window.addEventListener('storage', (event) => {
    if (!event.key || event.key.startsWith(STORAGE_PREFIX)) {
      if (event.key) {
        cachedSeqs.delete(event.key.slice(STORAGE_PREFIX.length));
      } else {
        cachedSeqs.clear();
      }
    }
  });

  window.addEventListener('pagehide', flushDirty);
  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      flushDirty();
    }
  });

  storageListenerInstalled = true;
}

function scheduleFlush(): void {
  if (flushTimer !== null) return;
  flushTimer = setTimeout(() => {
    flushTimer = null;
    flushDirty();
  }, FLUSH_DELAY_MS);
}

export function getLastEventSeq(sessionId: string): number | null {
  installListeners();
  if (cachedSeqs.has(sessionId)) {
    return cachedSeqs.get(sessionId) ?? null;
  }

  const storage =
    typeof globalThis.localStorage === 'undefined' ? null : globalThis.localStorage;
  if (!storage) return null;

  const raw = storage.getItem(storageKey(sessionId));
  if (!raw) return null;

  const seq = Number(raw);
  if (!Number.isFinite(seq)) return null;

  cachedSeqs.set(sessionId, seq);
  return seq;
}

export function recordLastEventSeq(sessionId: string, seq: number): void {
  installListeners();
  const current = cachedSeqs.get(sessionId);
  if (current != null && seq <= current) return;

  cachedSeqs.set(sessionId, seq);
  dirtySessions.add(sessionId);
  scheduleFlush();
}

export function flushLastEventSeq(sessionId?: string): void {
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }

  if (sessionId) {
    if (!dirtySessions.has(sessionId)) return;
    dirtySessions.delete(sessionId);
    const seq = cachedSeqs.get(sessionId);
    const storage =
      typeof globalThis.localStorage === 'undefined' ? null : globalThis.localStorage;
    if (!storage || seq == null) return;
    try {
      storage.setItem(storageKey(sessionId), String(seq));
    } catch {
      dirtySessions.add(sessionId);
    }
    return;
  }

  flushDirty();
}
