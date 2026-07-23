import '@testing-library/jest-dom';

// localStorage is not available for opaque origins in jsdom / Node 22 without extra flags.
// Provide a simple in-memory stub so any test that needs it can use it.
const _store = {};
const localStorageMock = {
  getItem:    (key)        => Object.prototype.hasOwnProperty.call(_store, key) ? _store[key] : null,
  setItem:    (key, value) => { _store[key] = String(value); },
  removeItem: (key)        => { delete _store[key]; },
  clear:      ()           => { Object.keys(_store).forEach(k => delete _store[k]); },
  get length() { return Object.keys(_store).length; },
  key:        (i)          => Object.keys(_store)[i] ?? null,
};
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true });

// jsdom has no ResizeObserver; recharts' ResponsiveContainer needs it. Stub it so
// components that render charts (e.g. IncidentKpiBar) don't blow up in tests.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
