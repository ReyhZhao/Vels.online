/* global __APP_VERSION__, __GIT_SHA__, __BUILD_TIME__ */
// Build-time version metadata, injected by Vite `define` (see vite.config.js).
// The `typeof` guards keep this safe if the constants are ever absent.

export const APP_VERSION =
  typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '0.0.0';

export const GIT_SHA = typeof __GIT_SHA__ !== 'undefined' ? __GIT_SHA__ : 'dev';

export const BUILD_TIME =
  typeof __BUILD_TIME__ !== 'undefined' ? __BUILD_TIME__ : null;

// Compact label for the UI, e.g. "v0.1.0 · a1b2c3d".
export const VERSION_LABEL = `v${APP_VERSION} · ${GIT_SHA}`;

// Fuller, human-readable string for tooltips / titles.
export const VERSION_DETAIL = [
  `Version ${APP_VERSION}`,
  `commit ${GIT_SHA}`,
  BUILD_TIME ? `built ${BUILD_TIME}` : null,
]
  .filter(Boolean)
  .join(' · ');
