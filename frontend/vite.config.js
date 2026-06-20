import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { fileURLToPath, URL } from 'node:url';
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const pkg = JSON.parse(
  readFileSync(fileURLToPath(new URL('./package.json', import.meta.url)), 'utf8')
);

// Short git commit the bundle was built from. Prefer an explicit build arg
// (set in CI / the production Dockerfile); fall back to a local git call when
// building on a checkout, and to 'dev' when neither is available (e.g. inside
// the dev container, which has no .git).
function gitSha() {
  if (process.env.VITE_GIT_SHA) return process.env.VITE_GIT_SHA;
  try {
    return execSync('git rev-parse --short HEAD', {
      stdio: ['ignore', 'pipe', 'ignore'],
    })
      .toString()
      .trim();
  } catch {
    return 'dev';
  }
}

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __GIT_SHA__: JSON.stringify(gitSha()),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['apple-touch-icon.png'],
      manifest: {
        name: 'Vels Online',
        short_name: 'Vels',
        description: 'Security monitoring and incident management',
        start_url: '/dashboard',
        display: 'standalone',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.js',
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': 'http://backend:8000',
      '/auth': 'http://backend:8000',
      '/login-redirect': 'http://backend:8000',
      '/static': 'http://backend:8000',
      '/django-admin': 'http://backend:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.js'],
    globals: true,
  },
});
