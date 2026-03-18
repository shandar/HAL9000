// HAL9000 Service Worker — enables PWA "Add to Home Screen"
// Minimal: just caches the shell for offline launch, all API calls go to network

const CACHE_NAME = 'hal9000-v3.2';
const SHELL_ASSETS = ['/assets/HAL-eye-192.png', '/assets/HAL-eye-512.png'];

self.addEventListener('install', (event) => {
  // Force immediate activation — don't wait for old SW to finish
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Delete ALL old caches
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API and stream requests always go to network
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // NEVER cache the main HTML page — always fetch fresh
  if (url.pathname === '/' || url.pathname.endsWith('.html')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Static assets: network first, cache fallback
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
