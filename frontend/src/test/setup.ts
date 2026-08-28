import '@testing-library/jest-dom/vitest'

/**
 * Node 25+ ships an experimental Web Storage that can replace jsdom's
 * `localStorage` with a stub missing `clear`/`setItem` when
 * `--localstorage-file` is unset. Production Docker builds use Node 20
 * (`backend/Dockerfile`); this polyfill keeps portable `vitest` scripts
 * working on developer machines without baking `NODE_OPTIONS=...` into
 * package.json (which is not Windows-portable).
 */
function installMemoryLocalStorage(): void {
  const store = new Map<string, string>()
  const memory: Storage = {
    get length() {
      return store.size
    },
    clear() {
      store.clear()
    },
    getItem(key: string) {
      return store.has(key) ? store.get(key)! : null
    },
    setItem(key: string, value: string) {
      store.set(String(key), String(value))
    },
    removeItem(key: string) {
      store.delete(key)
    },
    key(index: number) {
      return [...store.keys()][index] ?? null
    },
  }

  Object.defineProperty(globalThis, 'localStorage', {
    value: memory,
    configurable: true,
    writable: true,
  })
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, 'localStorage', {
      value: memory,
      configurable: true,
      writable: true,
    })
  }
}

try {
  const ls = globalThis.localStorage
  if (
    !ls ||
    typeof ls.getItem !== 'function' ||
    typeof ls.setItem !== 'function' ||
    typeof ls.removeItem !== 'function' ||
    typeof ls.clear !== 'function'
  ) {
    installMemoryLocalStorage()
  } else {
    // Probe: Node's broken stub can throw or no-op incorrectly.
    ls.setItem('__mf_ls_probe__', '1')
    if (ls.getItem('__mf_ls_probe__') !== '1') {
      installMemoryLocalStorage()
    } else {
      ls.removeItem('__mf_ls_probe__')
    }
  }
} catch {
  installMemoryLocalStorage()
}
