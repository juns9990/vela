// Vela Service Worker · v0.12.0
// 데스크톱 PWA 설치를 위한 최소 기능 SW + 네트워크-우선 캐시 전략

const CACHE_NAME = 'vela-cache-v0.12.0';
const CORE_ASSETS = [
  './vela-prototype.html',
  './vela-manifest.json',
  './vela-icon.svg'
];

// 설치: 핵심 리소스 캐싱
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(CORE_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

// 활성화: 이전 캐시 삭제
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(names => Promise.all(
        names.filter(n => n !== CACHE_NAME).map(n => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

// fetch: 네트워크 우선, 실패 시 캐시 폴백 (PWA 설치 요건)
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response && response.status === 200 && response.type === 'basic') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then(cached => cached || new Response('오프라인', { status: 503 })))
  );
});
