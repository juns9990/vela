# 벨챗 v2.8.4 — "알 수 없는 provider" 수정 (auto 미해석 경로 전수 소탕)

## 증상과 원인

Groq·Gemini 키를 둘 다 등록하고 자동 모드로 저장하면 **`✕ 알 수 없는 provider`**.

`✕` 접두어가 범인을 바로 가리킨다. 이 형식은 `setKeyStatus()` 에서만 나온다.

```js
setKeyStatus((r.ok ? '✓ ' : '✕ ') + r.msg, …);
```

그 값을 만든 곳은 `runKeyTest()` 였다.

```js
async function runKeyTest() {
  const provider = $('#inputProvider').value;   // ← 자동 모드면 'auto'
  …
  const r = await testApiKey(provider, key, model);
}

async function testApiKey(provider, key, model) {
  const cfg = LLM_CONFIG[provider];
  if (!cfg) return { ok: false, msg: '알 수 없는 provider' };   // ← 여기
}
```

**`'auto'` 는 UI 의 개념이지 회사 이름이 아니다.** `LLM_CONFIG` 에 그런 항목은 없다.
자동 모드로 키를 저장하면 저장 직후 연결 테스트가 돌고, 거기서 바로 터진다.
즉 **자동 모드를 켠 사람은 키를 저장하는 순간 무조건 이 오류를 본다.**

### v2.8.3 에서 왜 못 잡았나

v2.8.3 은 `state.provider === 'auto'` 를 **호출 계층(callLLM)** 에서 제대로 처리했다.
`resolveRoute()` 가 auto 를 실제 회사로 풀어주고, route 없이 호출해도
`opts.route || resolveRoute({})` 로 받아낸다. 그래서 **대화는 정상 동작한다.**

빠뜨린 건 **설정 계층**이었다. 거기서는 `state` 가 아니라 `#inputProvider` 의
드롭다운 값을 직접 읽어 provider 로 넘기고 있었고, 그 값은 `'auto'` 일 수 있다.
v2.8.3 테스트는 라우팅 엔진만 검증했지 설정 계층의 인자 흐름은 보지 않았다.

---

## 원인 조사 — 'auto' 가 도달할 수 있는 경로 전수

`provider` 를 인자로 받는 함수를 전부 뽑아 호출부를 역추적했다.

### 설정 계층 — 실제로 깨져 있던 곳 (5건)

1. **`runKeyTest()` → `testApiKey('auto', …)`** — 보고된 그 오류. `LLM_CONFIG['auto']` 없음.
2. **`runKeyTest()` → `chosenModelValue('auto')`** — `defaultModelFor('auto')` 가 빈 문자열을
   돌려줘, 통과하더라도 **모델 이름 없이** 테스트가 나갔다.
3. **`runModelList()` → `fetchModelList('auto', key)`** — `cfg.modelsUrl` 이 없어 `null`.
   "모델 목록을 가져오지 못했습니다" 로 조용히 잘못 안내.
4. **`showKeyQr()` → `buildKeyPayload('auto', key)`** — QR 에 `VC1|auto|키` 가 담긴다.
   받는 기기가 어느 회사 키인지 알 수 없어 자동 판별이 실패한다.
5. **모델 초기화(↺) → `defaultModelFor($('#inputProvider').value)`** — 빈 문자열.
   버튼을 누르면 모델 칸이 비어버린다.

### 런타임 계층 — 기능이 저하되던 곳 (1건)

6. **`rescueUnknownModel()` → `fetchModelList(state.provider, state.apiKey)`** —
   자동 모드에서 `state.provider` 는 `'auto'`, `state.apiKey` 는 대표값일 뿐이다.
   404 자기회복(v2.8.2)이 자동 모드에서만 조용히 무력화돼 있었다.

### 부작용 — 조사 중에 같이 발견 (2건)

7. **QR 스캔 / 클립보드 붙여넣기** — 키에서 회사를 알아내면
   `$('#inputProvider').value = parsed.provider` 로 **사용자를 자동 모드에서 끌어내렸다.**
   키 하나 넣었다고 라우팅 설정이 바뀌면 안 된다.

### 확인 결과 이상 없던 곳

- `callLLM()` — route 없이 불려도 `resolveRoute({})` 가 auto 를 푼다.
  **회의록·전문가 직함·언어 가드 재생성은 원래 정상이었다.**
- TTS(`speakMessage`) — Web Speech API 라 provider 와 무관.
- 내보내기·세션 저장 — API 호출 없음.
- `normalizeMessagesForProvider` / `describeApiError` / `pickModelForWeight` —
  전부 route 에서 provider 를 받으므로 실제 회사만 온다.

---

## 수정 — 두 겹

### ① 호출부를 바로잡는다 (진짜 수정)

**규칙: `provider` 를 인자로 받는 함수는 실제 회사만 받는다.**

설정 계층은 이미 `settingsKeyTarget()` 을 갖고 있었다 (v2.8.3에서 키 저장 대상을
분리하며 만든 것). **키가 실제로 묶여 있는 회사**를 돌려주는 함수다.
`#inputProvider.value` 를 그대로 쓰던 5곳을 전부 이걸로 바꿨다.

```js
const provider = settingsKeyTarget();   // 'auto' 가 아니라 실제 회사
```

연결 테스트가 묻는 건 "이 키가 **이 회사**에서 통하나"이지 "자동 모드가 유효한가"가
아니다. 질문 자체가 회사 단위라서 이게 의미상으로도 맞다.

QR·붙여넣기는 `focusKeyEditorOn()` 하나로 합쳤다.

```js
function focusKeyEditorOn(provider) {
  if (sel.value === AUTO_PROVIDER) {
    $('#inputKeyTarget').value = provider;   // 자동 모드는 유지하고 편집 대상만 옮긴다
  } else {
    sel.value = provider;
  }
  renderSettingsModalForProvider(settingsKeyTarget());
}
```

### ② 안전망 — 'auto' 가 와도 그 자리에서 해석 (요청 3)

호출부를 다 고쳤어도, 앞으로 추가될 코드가 또 빠뜨릴 수 있다.
그래서 **API 계층 입구에 문을 세웠다.**

```js
function realProvider(p) {
  if (p && p !== AUTO_PROVIDER && LLM_CONFIG[p]) return p;
  const r = resolveRoute({});
  if (r) return r.provider;
  return configuredProviders()[0] || REAL_PROVIDERS[0];
}
```

**에러가 아니라 해석이다.** 사용자는 아무 잘못이 없다 —
잘못은 우리 코드가 UI 개념을 API 계층까지 흘려보낸 것이고,
그 대가를 사용자가 "알 수 없는 provider" 로 치를 이유가 없다.

7개 진입점에 걸었다: `providerEndpoint` · `providerHeaders` · `testApiKey` ·
`fetchModelList` · `defaultModelFor` · `buildKeyPayload` · `rescueUnknownModel`.

`realProvider` 는 `resolveRoute()` 를 그대로 쓴다 — **auto 해석 로직은 여전히 한 곳뿐**이다.
안전망이 두 번째 해석 규칙을 만들면 그게 다음 버그가 된다.

> **무한재귀 확인** — `defaultModelFor('auto')` → `realProvider` → `resolveRoute`
> → `providerModelOf(실제회사)` → `defaultModelFor(실제회사)` 에서 `LLM_CONFIG` 를
> 찾으므로 즉시 끝난다. 테스트로 고정했다.

---

## 테스트 — 조합 구멍이 다시 안 생기게 (요청 4)

이번 버그의 성격이 중요하다. **단위로는 전부 옳았다.**
`resolveRoute` 도, `testApiKey` 도 각자 정상이다.
"자동 모드 × 설정 계층"이라는 **조합**에서만 드러났다.

그래서 새 테스트는 단위가 아니라 **조합을 훑는다.**
자동 모드 상태(Groq+Gemini 키)를 만들고, provider 를 받는 모든 진입점에
`'auto'` 를 **직접 먹여서 실행한다.**

`test-v284.js` — 39건

- **realProvider (6)** — `'auto'`/`undefined`/`''`/없는이름/실제이름/**키 0개**
- **각 진입점 (8)** — `providerEndpoint`·`providerHeaders`·`defaultModelFor`·
  `buildKeyPayload`·`rankModelNames` 에 auto 직접 투입.
  **결과 문자열에 `auto` 가 단 한 글자도 없는지**까지 확인
- **testApiKey (3)** — 이번 버그의 현장. `'알 수 없는 provider'` 가 안 나오고
  실제 연결까지 가는지, 요청 URL 에 `auto` 가 없는지
- **fetchModelList (2)** — auto 로 불러도 `null` 이 아닌지, URL 이 실제 회사 것인지
- **callLLM route 없이 (4)** — 옛 호출부(회의록·전문가 직함) 시뮬레이션.
  가짜 `fetch` 로 **실제로 나간 URL·헤더·본문**을 검사
- **사진·폴백 (4)** — vision 라우팅과 쿨다운 후에도 실제 회사만
- **고정 모드 (3)** — Groq 고정이 v2.8.3 과 똑같은지 (회귀 방지)
- **소스 구조 (9)** — raw `#inputProvider.value` 사용처가 저장 핸들러 하나뿐인지,
  5개 호출부가 `settingsKeyTarget` 을 쓰는지, `focusKeyEditorOn` 일원화,
  자동 모드에서 키를 넣어도 provider 선택이 안 바뀌는지

가짜 `fetch` 로 **실제 요청을 가로채 검사한다**는 게 핵심이다.
"코드에 이런 문자열이 있다"가 아니라 "이 값이 네트워크로 나갔다"를 본다.

### 전체 — 248건 통과

`regress` 37 · v2.8 23+21 · v2.8.1 31 · v2.8.2 47 · v2.8.3 50 · **v2.8.4 39**.

> `test-v282` 가 한 번 깨졌는데, `fetchModelList` 가 이제 `realProvider` 를 부르는데
> 그 하네스에 없어서였다. auto 검증은 v2.8.4 담당이므로 항등 함수를 넣어 분리했다.

---

## 실기기 확인 목록

**API 키가 없어 실제 연결 테스트는 못 했다.** 아래가 이번 수정의 핵심 확인이다.

1. Groq·Gemini 키 둘 다 등록 → **자동 모드로 저장** → `✕ 알 수 없는 provider` 가 안 뜨는지 ← **핵심**
2. 자동 모드에서 `🔌 연결 테스트` → 지금 고른 "관리할 회사" 기준으로 정상 동작하는지
3. 자동 모드에서 `📋 쓸 수 있는 모델 조회` → 목록이 뜨는지 (v2.8.3 에선 실패했다)
4. 자동 모드에서 모델 `↺` 버튼 → 모델 칸이 비지 않고 기본값이 들어오는지
5. 자동 모드에서 `📱 키를 QR로 표시` → 다른 기기로 스캔 → **회사가 올바로 잡히는지**
6. 자동 모드에서 QR 스캔·클립보드 붙여넣기 → **자동 모드가 유지되고** 키 대상만 바뀌는지
7. 자동 모드로 대화 → 정상 (v2.8.3 에서도 되던 것 — 회귀 확인)
8. 자동 모드에서 없는 모델 이름 저장 후 대화 → 404 구제 칩에 **모델 목록이 실려 나오는지**
9. 고정 모드(Groq/Gemini/Claude)로 전환 → v2.8.3 과 동일한지
10. `localStorage` 에 `vela.boardroom.apiKey.auto` 가 **없는지** (v2.8.3 에서 이미 방지)

---

## 손댄 곳

| 파일 | 내용 |
|---|---|
| `vela-boardroom-prototype.html` | `realProvider()` 안전망 · 설정 계층 5곳을 `settingsKeyTarget()` 으로 · `focusKeyEditorOn()` 일원화 · `rescueUnknownModel` 이 실패 회사를 받도록 · 버전 2.8.4 |
| `vela-boardroom-sw.js` | 스탬프가 `BUILD_ID` 갱신 |
| `velchat-v2.8.4-notes.md` | 이 문서 |
