# 벨챗 v2.8.3 — 하이브리드 자동 라우팅 + 무료 한도 대응

회사마다 잘하는 게 다르고 무료 한도도 따로 논다.

- **Groq** — 텍스트가 가장 빠르다. 사진은 못 본다.
- **Gemini** — 사진을 보고 무료 티어가 있다. 분당 한도가 빡빡하다.
- **Anthropic** — 품질 최고, 웹 검색 가능. 유료라 한도가 넉넉하다.

**사용자가 메시지마다 이걸 따져가며 provider 를 바꿔 끼울 수는 없다.**
그건 앱이 할 일이다.

---

## 1. 구조 변경 — provider 가 전역에서 메시지 단위로

v2.8.2 까지 `callLLM()` 은 `state.provider` / `state.apiKey` / `state.model` 을 직접 읽었다.
전역이 하나뿐이니 **한 대화 안에서 회사를 바꿀 방법이 없었다.**

그래서 **route 객체**를 도입했다.

```js
{ provider, key, model, cfg }
```

`callLLM(prompt, msgs, { route })` 로 받는다. `route` 가 없으면 `resolveRoute({})` 가
state 에서 만들어준다 — 회의록 같은 옛 호출부는 손대지 않아도 그대로 동작한다.

`resolveRoute()` 가 이 버전의 심장이다.

```js
function resolveRoute({ needsVision, exclude }) {
  if (!isAutoMode()) { /* 고정 모드는 state 그대로 — 수동 선택은 하나도 안 바뀐다 */ }
  const order = needsVision ? ROUTING_RULES.vision : ROUTING_RULES.text;
  const usable = order.filter(p => !excluded(p) && providerKeyOf(p));
  const ready  = usable.filter(providerAvailable);      // 쿨다운 중이 아닌 곳
  if (ready.length) return build(ready[0]);
  // 전부 쉬는 중이면 가장 빨리 풀리는 곳이라도 준다 — 후보 0 은 곧 침묵이다
  return build(soonestToRecover(usable));
}
```

우선순위는 CONFIG 다.

```js
text:   ['groq', 'gemini', 'anthropic'],   // 글만 있는 메시지
vision: ['gemini', 'anthropic'],           // 사진이 붙은 메시지
```

**`vision` 목록에 groq 이 없는 게 요점이다.** 사진을 못 보는 곳은 그 상황에서
아예 후보가 아니다 — 불러봐야 헛돈다.

---

## 2. 자동 모드의 UI

provider 선택 맨 위에 `🔀 자동 (추천)` 을 넣었다. **기존 고정 선택도 그대로 남아 있다.**

### 자동 모드에서 키는 어떻게 관리하나

여기서 함정이 하나 있었다. 저장 코드가 이랬다.

```js
localStorage.setItem(apiKeyStorageKey(newProvider), newKey);
```

`newProvider` 가 `'auto'` 면 **`vela.boardroom.apiKey.auto` 라는 쓰레기 칸**이 생기고,
정작 실제 회사 키는 아무데도 저장되지 않는다.

그래서 "키·모델을 관리할 회사" 보조 선택(`#inputKeyTarget`)을 뒀다.
자동 모드일 때만 열리고, 아래 키/모델 칸이 여기에 묶인다.
저장은 `settingsKeyTarget()` 이 돌려주는 **진짜 회사**로 나간다.

처음 열면 **키가 없는 회사를 먼저** 보여준다 — 지금 할 일이 그거니까.
각 항목에 `· 키 있음 / · 키 없음` 을 붙여 열어보지 않아도 상태를 알 수 있게 했다.

`state.apiKey` 도 자동 모드에서는 의미가 달라진다. 전송 가능 여부를 판단하던
`if (!state.apiKey)` 를 전부 `hasAnyKey()` 로 바꿨다 —
자동 모드에서는 "어느 회사든 키가 하나라도 있나"가 기준이다.

### 라우팅 내역은 설정에만

> 어느 쪽이 답했는지 궁금할 사용자를 위해 — 단, **대화 화면에는 표시하지 않는다.**

단톡방에 "이번엔 Groq이 답했습니다" 같은 게 끼면 몰입이 깨진다.
그건 앱의 사정이지 대화의 일부가 아니다.

설정 → 일반 하단에 최근 12건이 쌓인다.

```
14:32 ·  Groq    서다현        412ms
14:32 ↪  Gemini  이준호        890ms      ← ↪ 는 폴백으로 넘어갔다는 뜻
14:31 ✕  Groq    이준호        429        ← 실패도 남는다
14:30 ·  Gemini  정민철 📷     1204ms     ← 📷 는 사진이 붙은 메시지
```

**성공만 남기면 반쪽짜리다.** "왜 이 메시지는 느렸지?"의 답이 실패 줄에 있다.

---

## 3. 폴백 — 기다리기 전에 옆집

이 함수에서 **순서가 전부**다.

```js
if (!failover) throw e;                    // ① 키·모델 오류는 옮겨봐야 똑같다
if (rec.spoke) throw e;                    // ② 이미 말이 나갔으면 되감지 않는다
tried.push(route.provider);
if (resolveRoute({ exclude: tried })) continue;   // ③ 안 써본 곳이 있으면 즉시 그쪽
await countdownWait(rec, waitMs, status);         // ④ 갈 곳이 없을 때만 기다린다
tried.length = 0;                                 //    다시 전부 후보로
```

- **①** 401(키 오류)이나 404(모델 없음)는 다른 회사로 가도 그대로다. 폴백 대상은
  `429 / 503 / 529` 와 네트워크 오류뿐이다.
- **②** 이게 중요하다. 이미 스트리밍으로 반쯤 나온 말을 처음부터 다시 쓰면
  **사용자 화면에서 글이 되감긴다.** 그건 오류보다 더 이상해 보인다.
- **③** 자동 모드에서 30초 기다리는 것보다 다른 회사가 0.5초에 답하는 게 낫다.
  요청서의 "재시도 전에 폴백 먼저"가 이 한 줄이다.
- **④** 지수 백오프. 전체 루프는 6회로 막아 무한 반복을 원천 차단한다.

실패한 provider 는 `coolDownProvider()` 로 잠시 후보에서 뺀다
(429 는 45초, 503 은 15초). 같은 벽에 계속 부딪히지 않게 하는 장치다.

---

## 4. 429 vs 503 — 성격이 다르다

- **429** — 내 한도 초과. **기다리면 반드시 풀린다.** 두 번까지 기다려본다 (4s → 8s).
- **503** — 저쪽 혼잡. 기다린다고 풀린다는 보장이 없다. 한 번만 짧게 보고 포기한다.

```js
const RETRY_RULES = {
  429: { tries: 2, baseMs: 4000, maxMs: 30000 },
  503: { tries: 1, baseMs: 1500, maxMs: 4000 },
  jitter: 0.25
};
```

**대기 시간은 저쪽이 알려준 값이 최우선이다.** 우리 추측보다 항상 낫다.

```js
function parseRetryAfterMs(res, raw) {
  // ① Retry-After 헤더 — 초 단위 숫자 또는 HTTP 날짜 (표준)
  // ② Groq — 본문에 "try again in 12.5s"
  // ③ Gemini — RetryInfo 의 "retryDelay": "17s"
  // 못 찾으면 0 → 호출부가 지수 백오프로 정한다
}
```

지터(±25%)를 섞는 이유: 세 명이 동시에 429 를 맞으면 셋 다 같은 순간에 깨어나
**또 같이 몰린다.** 흩어뜨려야 한다.

### 기다리는 동안 — 카운트다운

그냥 멈춰 있으면 사용자는 앱이 죽은 줄 안다.
"생각하는 중…" 자리에 남은 초를 띄운다.

```
무료 한도 — 12초 후 재시도
```

`rec.setStatus()` → `bubble.setStatus()` 로 흐른다.
아직 표시 전인 턴(미리 걸어둔 것)은 문구를 들고 있다가 **붙는 순간 보여준다.**
이미 글자가 나오기 시작했으면 건드리지 않는다 — 말풍선 머리를 덮어쓸 수 없다.
타이핑 표시는 그대로 유지된다.

### 실패 안내는 말풍선이 아니라 시스템 칩

페르소나가 "⚠ 무료 한도 초과"라고 말하는 건 이상하다.
그건 **사람의 발언이 아니라 앱의 사정**이다.

한도·혼잡·네트워크 실패는 `quiet` 로 표시해 말풍선 대신 시스템 칩으로 나간다.
그것도 `noteQuietFailure()` 가 **메시지당 한 번만** 띄운다 —
셋이 답하다 셋 다 걸리면 같은 칩이 세 번 뜬다. 그건 알림이 아니라 소음이다.

---

## 5. Gemini 페이싱

무료 분당 한도는 **동시에 몰릴 때** 터진다. 두 갈래로 막는다.

**① 프리페치 제외** — v2.8 의 "미리 걸기"는 두 번째 응답자 호출을 첫 사람이
말하는 동안 진행시킨다. 빠르지만, 같은 순간에 두 콜이 나간다는 뜻이고
**그게 정확히 분당 한도를 치는 방식**이다.

```js
prefetch: { anthropic: true, gemini: false, groq: false }
```

유료라 한도가 넉넉한 Anthropic 만 허용한다. 자동 모드에서는
"지금 가장 먼저 고를 곳"을 기준으로 판단한다.

**② 콜 간 최소 간격** — Gemini 는 1.4초.

```js
async function paceProvider(provider) {
  const last = providerLastCallAt[provider] || 0;
  const wait = last + gap - Date.now();
  // 다음 호출자를 위해 "지금 쏜다"를 먼저 예약한다 (동시 진입해도 줄이 선다)
  providerLastCallAt[provider] = Math.max(Date.now(), last + gap);
  if (wait > 0) await sleep(wait);
}
```

**예약을 먼저 쓰고 나중에 기다리는 순서가 핵심이다.** 두 호출이 같은 틱에 들어와도
두 번째가 첫 번째의 예약을 보고 그 뒤에 줄을 선다.
테스트로 확인했다 — 동시 진입 두 건이 2800ms(= 1400 × 2) 만큼 벌어진다.

---

## 6. 우아한 축소 — 전멸 침묵 금지

한도에 걸렸을 때 최악은 **아무도 말하지 않는 것**이다.
방이 조용한 것과 앱이 고장 난 것은 사용자에게 똑같이 보인다.

**① 한도를 만나면 남은 응답자를 접는다.** 어차피 같은 벽에 부딪힌다.
셋이 다 실패하느니 한 명이 답하고 끝나는 게 낫다.

**② 그래도 아무도 못 말했으면 한 명만 다시.** 짧은 무게(`casual`)로 —
다시 한도를 치지 않게 최소 비용으로 간다.

```js
if (DEGRADE_RULES.lastResort && spoke.length === 0 && (quotaHit || anyOutage)) { … }
```

---

## 7. 자기 리뷰에서 잡은 버그 둘

테스트를 다 통과한 뒤 코드를 다시 읽다가 두 개를 찾았다.

**① 사진 때문에 대화가 멈추는 경로**
자동 모드에서 Groq 키만 있는데 사진을 올리면,
`needsVision = true` → vision 후보 0 → `resolveRoute` 가 `null` →
**모든 턴이 즉시 실패.** 사진 하나 때문에 방이 죽는다.

```js
const needsVision = !!opts.hasImages && providerSupportsVision();
```

볼 수 있는 키가 아예 없으면 vision 라우팅을 요구하지 않는다.
그 경우 히스토리에서 이미지는 이미 빠졌고 "사진을 못 본다" 안내도 나갔으므로,
**텍스트로라도 답하는 게 맞다.**

**② 마지막 구제가 429 에서만 돌았다**
`quotaHit` 만 보고 있어서, 503 이나 네트워크 장애로 전멸하면
마지막 한 명 시도가 아예 안 걸렸다. "전부 실패 시"라는 요건에 못 미친다.
`anyOutage` 를 따로 세어 조용한 실패 전체를 포함하도록 고쳤다.

둘 다 테스트가 못 잡는 종류였다 — 단위로는 각각 옳게 동작하고,
**조합했을 때만 드러나는 구멍**이었다.

---

## 8. 확인한 것

### 신규 테스트 — 50건 (`test-v283.js`)

라우팅 엔진을 통째로 떼어내 **가짜 localStorage 위에서 실제로 돌렸다.**

- **자동 라우팅 (7)** — 텍스트→Groq, 사진→Gemini, 키 조합별 후보 계산
- **고정 모드 (3)** — 사진이어도 그 provider, state 값 사용 (수동 선택 불변 확인)
- **폴백 (6)** — exclude 체인, 쿨다운, **전부 쉬는 중이어도 후보를 준다**(전멸 금지)
- **페이싱 (6)** — 간격 0 인 곳은 안 기다림, **동시 진입 시 줄서기**(실측 2800ms)
- **parseRetryAfterMs (6)** — 헤더/Groq 문구/Gemini retryDelay/ms/HTTP 날짜/없음
- **재시도 규칙 (5)** — 429 두 번·503 한 번, 대기 길이 대소, 지터
- **소스 구조 (17)** — **폴백이 재시도보다 앞에 오는지**, 되감기 금지,
  키 오류는 폴백 안 함, 성공·실패 양쪽 기록, 라우팅 내역이 대화에 안 뜨는지,
  `apiKey.auto` 방지, 게이트 교체

### 회귀 — 159건

`regress.js` 37 · v2.8 23+21 · v2.8.1 31 · v2.8.2 47. **합계 209건 통과.**

> 회귀에서 처음 5건이 실패했는데 **전부 검사가 낡은 것**이었다 —
> `askOnce` → `askWithFailover` 개명, 사진 안내 문구 변경,
> 저장 대상이 `newProvider` → `keyTarget` 으로 바뀐 것.
> 코드가 아니라 단언을 새 이름으로 고쳤다.

### 실호출은 못 했다

**API 키가 없어 실제 429/503 을 받아보지는 못했다.**
라우팅·페이싱·백오프 계산은 합성 데이터로 검증했지만,
진짜 한도에 부딪혔을 때의 동작은 확인이 필요하다.

**남은 확인 목록**

1. Groq + Gemini 키 둘 다 등록 → 자동 선택 → 글 메시지가 Groq 으로 가는지 (설정 내역)
2. 사진을 붙여 전송 → Gemini 로 가는지, 페르소나가 사진 내용을 언급하는지
3. Gemini 로 빠르게 연속 전송 → 429 유발 → **카운트다운이 뜨고 자동 복구되는지**
4. 그때 다른 키가 있으면 기다리지 않고 **바로 넘어가는지** (내역에 ↪ 표시)
5. 한도 실패 시 **말풍선이 아니라 시스템 칩**이 한 번만 뜨는지
6. 전부 실패 상황 → 최후의 한 명이 짧게라도 답하는지
7. Groq 키만 있는 상태에서 사진 전송 → **멈추지 않고 텍스트로 답하는지** (버그 ①)
8. 자동 모드에서 키 저장 → `localStorage` 에 `apiKey.auto` 가 **안 생기는지**
9. 고정 모드(Groq/Gemini)로 돌려도 v2.8.2 와 똑같이 동작하는지
10. 설정 → 라우팅 내역이 쌓이는지, **대화 화면에는 아무것도 안 뜨는지**
11. **회귀** — 스트리밍·프리페치·2단 모델(v2.8) · 창 모드(v2.8.1) · 모델 조회(v2.8.2) · 키보드(v2.7.2)

### 되돌리는 법

- provider 를 고정으로 바꾸면 v2.8.2 동작 그대로다 (자동 모드만 새 경로를 탄다)
- `ROUTING_RULES.prefetch` 를 전부 `true` → v2.8 의 미리 걸기 복귀
- `ROUTING_RULES.minGapMs` 를 전부 `0` → 페이싱 없음
- `DEGRADE_RULES.lastResort = false` → 최후의 한 명 없음

---

## 손댄 곳

| 파일 | 내용 |
|---|---|
| `vela-boardroom-prototype.html` | route 객체 도입 · `resolveRoute`/`paceProvider`/`coolDownProvider` · `ROUTING_RULES`/`RETRY_RULES`/`DEGRADE_RULES` · 폴백·백오프·카운트다운 · 자동 모드 UI·키 대상 분리 · 라우팅 내역 · `hasAnyKey` · 버전 2.8.3 |
| `vela-boardroom-sw.js` | 스탬프가 `BUILD_ID` 갱신 |
| `velchat-v2.8.3-notes.md` | 이 문서 |
