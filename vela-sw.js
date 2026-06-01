// Vela Service Worker · v0.21.0
// 이미지 매주 회전 + PWA 캐시 동적 리소스 네트워크 우선

const CACHE_VERSION = 'v0.23.0';
const CACHE_NAME = `vela-cache-${CACHE_VERSION}`;

// 정적 리소스만 캐싱 (HTML/매니페스트/아이콘)
const STATIC_ASSETS = [
  './vela-prototype.html',
  './vela-manifest.json',
  './vela-icon.svg'
];

// 동적 리소스 패턴 (절대 캐시 안 함, 항상 네트워크)
const DYNAMIC_PATTERNS = [
  /vela-issue.*\.json$/,
  /vela-archive\.json$/,
  /vela-rss\.xml$/
];

function isDynamicResource(url) {
  return DYNAMIC_PATTERNS.some(pattern => pattern.test(url));
}

// 설치: 정적 리소스만 캐싱
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

// 활성화: 이전 캐시 모두 삭제 + 즉시 모든 탭 제어
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(names => Promise.all(
        names.filter(n => n !== CACHE_NAME).map(n => {
          console.log('[Vela SW] Deleting old cache:', n);
          return caches.delete(n);
        })
      ))
      .then(() => self.clients.claim())
      .then(() => {
        return self.clients.matchAll({ type: 'window' }).then(clients => {
          clients.forEach(client => {
            client.postMessage({ type: 'SW_UPDATED', version: CACHE_VERSION });
          });
        });
      })
  );
});

// fetch 전략:
// - 동적 리소스 (issue/archive/rss): 무조건 네트워크
// - 정적 리소스: 네트워크 우선, 실패 시 캐시
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = event.request.url;

  if (isDynamicResource(url)) {
    event.respondWith(
      fetch(event.request, { cache: 'no-store' })
        .catch(() => caches.match(event.request))
    );
    return;
  }

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
