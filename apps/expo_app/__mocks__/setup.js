// setup.js - global test setup
global.__DEV__ = true;

// Mock localStorage
global.localStorage = {
  _store: {},
  getItem: (key) => global.localStorage._store[key] ?? null,
  setItem: (key, value) => { global.localStorage._store[key] = String(value); },
  removeItem: (key) => { delete global.localStorage._store[key]; },
  clear: () => { global.localStorage._store = {}; },
};

// Mock window.matchMedia
global.matchMedia = global.matchMedia || function() {
  return {
    matches: false,
    addListener: jest.fn(),
    removeListener: jest.fn(),
  };
};
