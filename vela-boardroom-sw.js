/* =============================================================
 * Vela Boardroom — Service Worker
 * v0.9.5
 *
 * 전략:
 * - HTML + manifest.json은 network-first (즉시 업데이트 반영)
 * - 아이콘/이미지는 cache-first (자주 안 바뀜)
 * - Anthropic API 요청은 절대 캐시하지 않음 (network-only)
 * - 폰트 CDN은 stale-while-revalidate (오프라인 대비)
 * ============================================================= */

const CACHE_VERSION = 'vela-boardroom-v0.9.5';
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

// HTML 또는 manifest인지 — network-first 대상
function isVersionedAsset(url) {
  const path = new URL(url).pathname;
  return path.endsWith('.html') || path.endsWith('manifest.json');
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
        console.warn('[boardroom-sw] precache partial:', e);
      }))
      .then(() => self.skipWaiting())
  );
});

/* ===== HTML이 SKIP_WAITING 명령 보내면 즉시 활성화 ===== */
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

/* ===== activate — 이전 보드룸 캐시만 정리 ===== */
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

  // 보드룸 자산 처리
  if (isBoardroomAsset(url)) {
    // HTML / manifest — network-first (즉시 업데이트 반영)
    if (isVersionedAsset(url)) {
      event.respondWith(
        fetch(req).then((fresh) => {
          if (fresh && fresh.ok && fresh.type === 'basic') {
            const clone = fresh.clone();
            caches.open(STATIC_CACHE).then((c) => c.put(req, clone));
          }
          return fresh;
        }).catch(() => caches.match(req)) // 오프라인 시 캐시 fallback
      );
      return;
    }

    // 이미지/아이콘 — cache-first (변경 적음)
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
