/* =============================================================
 * Vela Boardroom — Service Worker
 * v0.4.0
 *
 * 전략:
 * - 보드룸 관련 정적 자산만 캐시 (다른 vela 앱과 격리)
 * - Anthropic API 요청은 절대 캐시하지 않음 (network-only)
 * - 폰트 CDN은 stale-while-revalidate (오프라인 대비)
 * ============================================================= */

const CACHE_VERSION = 'vela-boardroom-v0.4.0';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const FONT_CACHE = `${CACHE_VERSION}-fonts`;

// 보드룸 핵심 자산 (precache 대상)
const BOARDROOM_ASSETS = [
  './vela-boardroom-prototype.html',
  './vela-boardroom-manifest.json',
  './vela-boardroom-icon-192.png',
  './vela-boardroom-icon-512.png',
  './vela-boardroom-icon-192-maskable.png',
  './vela-boardroom-icon-512-maskable.png',
  './vela-boardroom-icon-180.png'
];

// 보드룸 자산 식별 — 다른 vela-* 파일은 건드리지 않음
function isBoardroomAsset(url) {
  const path = new URL(url).pathname;
  return path.includes('vela-boardroom');
}

function isFontRequest(url) {
  return /fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net.*pretendard/i.test(url);
}

function isAnthropicAPI(url) {
  return /api\.anthropic\.com/i.test(url);
}

/* ===== install ===== */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(BOARDROOM_ASSETS).catch((e) => {
        // 일부 자산이 없어도 SW 설치는 진행
        console.warn('[boardroom-sw] precache partial:', e);
      }))
      .then(() => self.skipWaiting())
  );
});

/* ===== activate — 이전 보드룸 캐시만 정리 (다른 vela 앱 캐시는 보존) ===== */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('vela-boardroom-') && !k.startsWith(CACHE_VERSION))
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

/* ===== fetch ===== */
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = req.url;

  // GET만 처리
  if (req.method !== 'GET') return;

  // Anthropic API — 절대 캐시 안 함, 무조건 네트워크
  if (isAnthropicAPI(url)) {
    return; // 기본 fetch 동작
  }

  // 보드룸 자산 — cache-first
  if (isBoardroomAsset(url)) {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) {
          // 백그라운드 갱신
          fetch(req).then((fresh) => {
            if (fresh && fresh.ok) {
              caches.open(STATIC_CACHE).then((c) => c.put(req, fresh.clone()));
            }
          }).catch(() => {});
          return cached;
        }
        return fetch(req).then((res) => {
          if (res && res.ok && res.type === 'basic') {
            const clone = res.clone();
            caches.open(STATIC_CACHE).then((c) => c.put(req, clone));
          }
          return res;
        });
      })
    );
    return;
  }

  // 폰트 — stale-while-revalidate
  if (isFontRequest(url)) {
    event.respondWith(
      caches.open(FONT_CACHE).then((cache) =>
        cache.match(req).then((cached) => {
          const network = fetch(req).then((fresh) => {
            if (fresh && fresh.ok) cache.put(req, fresh.clone());
            return fresh;
          }).catch(() => cached);
          return cached || network;
        })
      )
    );
    return;
  }

  // 그 외 (다른 vela-* 파일 등) — 보드룸 SW가 간섭하지 않음
});
