type JsonMap<TValue> = Record<string, TValue>;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function createJsonMapStore<TValue>(
  storageKey: string,
  onWriteError?: (error: unknown) => void,
) {
  let cachedMap: JsonMap<TValue> | null = null;
  let cachedRaw: string | null = null;
  let storageListenerInstalled = false;

  const invalidate = () => {
    cachedMap = null;
    cachedRaw = null;
  };

  const installStorageListener = () => {
    if (storageListenerInstalled || typeof window === 'undefined') return;
    window.addEventListener('storage', (event) => {
      if (event.key === storageKey || event.key === null) {
        invalidate();
      }
    });
    storageListenerInstalled = true;
  };

  const readAll = (): JsonMap<TValue> => {
    installStorageListener();
    if (cachedMap !== null) return cachedMap;

    const storage =
      typeof globalThis.localStorage === 'undefined' ? null : globalThis.localStorage;
    if (!storage) {
      cachedMap = {};
      cachedRaw = null;
      return cachedMap;
    }

    try {
      const raw = storage.getItem(storageKey);
      cachedRaw = raw;
      if (!raw) {
        cachedMap = {};
        return cachedMap;
      }
      const parsed = JSON.parse(raw);
      cachedMap = isPlainObject(parsed) ? (parsed as JsonMap<TValue>) : {};
      return cachedMap;
    } catch {
      cachedMap = {};
      cachedRaw = null;
      return cachedMap;
    }
  };

  const writeAll = (map: JsonMap<TValue>): void => {
    installStorageListener();
    cachedMap = map;

    const storage =
      typeof globalThis.localStorage === 'undefined' ? null : globalThis.localStorage;
    if (!storage) return;

    try {
      const serialized = JSON.stringify(map);
      if (serialized === cachedRaw) return;
      storage.setItem(storageKey, serialized);
      cachedRaw = serialized;
    } catch (error) {
      onWriteError?.(error);
    }
  };

  const setEntry = (key: string, value: TValue): void => {
    const map = readAll();
    map[key] = value;
    writeAll(map);
  };

  const deleteEntry = (key: string): void => {
    const map = readAll();
    if (!(key in map)) return;
    delete map[key];
    writeAll(map);
  };

  const moveEntry = (fromKey: string, toKey: string): void => {
    const map = readAll();
    if (!(fromKey in map)) return;
    map[toKey] = map[fromKey];
    delete map[fromKey];
    writeAll(map);
  };

  return {
    readAll,
    writeAll,
    setEntry,
    deleteEntry,
    moveEntry,
    invalidate,
  };
}
