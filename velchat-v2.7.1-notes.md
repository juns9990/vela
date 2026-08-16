# 벨챗 v2.7.1 — PC 설치형 카톡식 창 모드

> 요청 제목은 "v2.6.1" 이었으나, 저장소는 이미 **v2.7.0** (API 키 등록 편의) 이 커밋된 상태였다.
> 버전을 2.6.1 로 되돌리면 앱 하단 상태줄·크레딧에 이전 버전이 찍히고,
> 서비스워커/캐시 로그를 볼 때 릴리스 순서가 뒤집혀 보인다.
> 그래서 같은 작업 내용을 **v2.7.1** (2.7.0 의 패치) 로 올렸다. 기능 범위는 요청 그대로다.

---

## 왜 만들었나

벨챗은 지금까지 **"무대 위에 놓인 중앙 카드"** 한 가지 모습만 있었다.
좌우로 그라데이션 배경이 넓게 보이고, 가운데 480px 짜리 카드가 채팅방이다.
브라우저 탭에서는 이게 맞다 — 탭은 문서를 보는 자리고, 카드는 "이 문서 안의 앱"이라는 신호다.

그런데 PWA 로 **설치한 창**에서는 이 모습이 어색하다.
설치 창은 이미 그 자체로 앱이다. 창 테두리가 곧 앱의 테두리인데
그 안에서 또 카드를 그리고 좌우에 배경을 깔면, 창 안에 창이 하나 더 있는 꼴이 된다.
카카오톡 PC 버전을 떠올려 보면 답이 분명하다 — **창을 열면 그 창이 곧 대화방이다.**

v2.7.1 은 그 한 가지를 고친다. 브라우저 탭에서는 지금까지의 카드형을 그대로 두고,
설치 창에서만 여백·라운드·그림자를 걷어내 셸이 창을 꽉 채우게 한다. 두 모드는 공존한다.

---

## 1. 두 모드를 가르는 스위치 — 변수 7개

레이아웃 규칙을 모드별로 두 벌 쓰면 반드시 한쪽만 고치는 사고가 난다.
그래서 **규칙 본문은 한 번만 쓰고, 값만 변수로 갈아끼우는** 구조로 짰다.

```css
:root {
  --stage-pad:    22px;                            /* 무대 위아래 여백 */
  --shell-max:    var(--shell-w, 480px);           /* 셸 최대 폭 */
  --shell-radius: 24px;
  --shell-shadow: 0 24px 64px var(--shadow), 0 3px 12px var(--shadow);
  --main-max:     1280px;
  --d-browser:    block;                           /* 탭에서만 보이는 것 */
  --d-window:     none;                            /* 창에서만 보이는 것 */
}
```

이 변수를 받아쓰는 레이아웃은 딱 세 덩어리다.

```css
.app-shell { max-width: var(--shell-max); }

@media (min-width: 560px) {
  body.chat-only { padding: var(--stage-pad) 0; }
  .app-shell {
    border-radius: var(--shell-radius);
    box-shadow:    var(--shell-shadow);
  }
}

body.chat-only main { max-width: var(--main-max); margin: 0 auto; }
```

창 모드에서는 이 변수들이 통째로 0/none 이 된다.

```css
@media (display-mode: standalone),
       (display-mode: window-controls-overlay),
       (display-mode: minimal-ui),
       (display-mode: fullscreen) {
  :root {
    --stage-pad: 0px; --shell-max: none; --shell-radius: 0px;
    --shell-shadow: none; --main-max: none;
    --d-browser: none; --d-window: block;
  }
}
```

`standalone` 하나만 쓰지 않은 이유:
`fullscreen` 과 `minimal-ui` 도 사용자 입장에서는 똑같이 "앱 창"이고,
`window-controls-overlay` 는 나중에 타이틀바를 직접 그리게 될 때를 대비한 자리다.
넷 중 어느 것이 켜져도 결과는 같아야 한다.

### `--main-max` 를 왜 따로 뒀나

`main` 은 매거진 시절부터 `max-width: 1280px; margin: 0 auto` 를 갖고 있었다.
셸이 최대 720px 일 때는 이 값이 닿을 일이 없어 아무도 눈치채지 못했다.
그런데 창 모드로 셸의 폭 제한을 풀면, 1440px 짜리 창에서 셸은 꽉 차는데
그 안의 `main` 이 1280px 에서 멈추면서 좌우에 80px 씩 빈 띠가 생긴다.
"창 전체를 채운다"는 약속이 정확히 여기서 깨진다. 그래서 같이 풀어준다.

---

## 2. iOS 보강 — `body.pwa-window`

데스크탑 Chrome/Edge 는 위 미디어 쿼리만으로 끝난다. 문제는 iOS Safari 다.
홈 화면에 추가한 앱에서도 `display-mode` 미디어 쿼리를 주지 않고
`navigator.standalone` 불리언만 준다. 그래서 JS 로 한 겹 덧댄다.

```js
const WINDOW_MODES = ['standalone', 'window-controls-overlay', 'minimal-ui', 'fullscreen'];

function isWindowMode() {
  if (window.navigator.standalone === true) return true;   // iOS 홈화면 앱
  return WINDOW_MODES.some(m => {
    try { return window.matchMedia('(display-mode: ' + m + ')').matches; } catch (e) { return false; }
  });
}

function applyWindowMode() {
  document.body.classList.toggle('pwa-window', isWindowMode());
}
```

`body.pwa-window` 는 위 `@media` 블록과 **똑같은 변수 묶음**을 다시 켠다.
중복되는 건 변수 선언 7줄뿐이고, 레이아웃 규칙은 여전히 한 벌이다.

`bindWindowMode()` 는 네 모드 각각의 `matchMedia` 에 `change` 리스너를 건다.
창 모드는 도중에 바뀔 수 있기 때문이다 — 전체화면 토글, 탭에서 앱으로 열기 등.
`addEventListener` 가 없는 구형 Safari 를 위해 `addListener` 폴백도 둔다.

CSS 가 주(主)이고 JS 는 보강이라는 순서가 중요하다.
스크립트가 어떤 이유로든 늦게 돌거나 실패해도, 데스크탑 설치 창은 이미 제 모습이다.

---

## 3. 좁은 창에서 버티기 (최소 320px)

설치 창은 사용자가 마음대로 줄인다. 카톡처럼 화면 구석에 세워 두려면
아주 좁혀도 **헤더 한 줄 · 입력독 한 줄 · 칩 줄바꿈**이 유지돼야 한다.

### 진짜 원인은 textarea 였다

```css
.chat-input { min-width: 0; }
```

`<textarea>` 는 `cols` 기본값(20)에 해당하는 min-content 폭을 주장한다.
flex 아이템의 `min-width` 기본값은 `auto` — 즉 min-content 아래로는 안 줄어든다.
독의 가용 폭이 그 아래로 내려가는 순간 `+ 🎤 → ` 버튼들이 창 밖으로 밀려난다.
320px 에서 계산하면 `버튼 116px + gap 21px + textarea 약 180px = 317px` 로
독 안쪽 폭(약 260px)을 넘어선다. `min-width: 0` 이 이 사슬을 끊는다.

같은 이유로 `.masthead-meta { min-width: 0 }`, `.app-shell { min-width: 0 }` 을 함께 걸었고,
`.brand-name`("벨챗")은 반대로 `flex-shrink: 0` 으로 못 박아 글자가 찌그러지지 않게 했다.

### 360px 이하 — 치수 한 단계 축소

| 대상 | 기존 | 360px 이하 |
|---|---|---|
| main / dock 좌우 패딩 | 14~16px | 10px |
| 첨부 버튼 | 36px | 32px |
| 마이크 | 40px | 34px |
| 전송 | 40px | 36px |
| 입력창 | 44px / 11·16px | 38px / 9·13px |
| 라우팅 칩 | 7·12px | 5·9px, 자간 0.04em |
| 브랜드 마크 | 30px | 26px |
| 헤더 아이콘 버튼 | 34px | 30px |

칩은 5개(자동·전원·페르소나 3)라 어차피 `flex-wrap` 으로 두 줄이 되지만,
자간을 줄여 한 줄에 3개까지 들어가게 했다.

### 330px 이하 — 방 제목 양보

```css
@media (max-width: 330px) {
  body.chat-only:not(.chrome-collapsed) .brand-room { display: none; }
}
```

펼침 상태에서는 방 제목이 `.chat-header` 에 이미 크게 떠 있다. 헤더에서 중복이다.
반대로 **접힘(몰입) 모드에서는 방 제목이 헤더의 유일한 신원**이므로 그대로 둔다.
`:not(.chrome-collapsed)` 한 줄이 그 구분을 한다.

---

## 4. 설정 안내 한 줄

`설정 → 일반` 탭 맨 위, 모드에 따라 둘 중 하나만 뜬다.

- 탭에서 열었을 때
  `💻 PC 앱으로 설치하면 카톡처럼 쓸 수 있어요 — 헤더의 앱 설치를 누르면 창 하나가 통째로 채팅방이 됩니다.`
- 설치 창에서 열었을 때
  `💻 PC 앱 창 모드로 실행 중이에요 — 창 크기가 곧 채팅창 크기입니다. 좁게 줄여 옆에 띄워두세요.`

전환은 `--d-browser` / `--d-window` 변수가 한다.

```css
.only-browser { display: var(--d-browser); }
.only-window  { display: var(--d-window); }

/* 모바일에선 PC 안내·너비 조절이 의미 없다 (위 규칙보다 뒤에 와야 이긴다) */
@media (max-width: 559px) { .pc-only { display: none; } }
```

마지막 `@media` 블록이 왜 다시 나오는지가 이 파일에서 유일하게 헷갈릴 지점이다.
원래 `.pc-only { display: none }` 은 파일 위쪽(v2.5 블록)에 있었는데,
`.only-browser` 규칙이 더 아래에 오면서 같은 특이도로 이겨 버린다.
그래서 좁은 화면 규칙을 `.only-browser` **뒤에** 한 번 더 선언해 순서로 되찾는다.

### 너비 슬라이더도 같이 감춘다

`설정 → 테마 → 채팅창 너비` 는 `.pc-only` 에 `.only-browser` 를 더해 창 모드에서 숨긴다.
창 모드에서는 `--shell-max: none` 이라 슬라이더를 움직여도 아무 일이 없다.
동작하지 않는 컨트롤을 보여주는 게 제일 나쁘다.

`applyShellWidth()` 는 손대지 않았다 — 값은 계속 `localStorage` 에 남아 있고,
브라우저 탭으로 돌아가면 마지막에 맞춰 둔 폭이 그대로 복원된다.

### 설치 직후 토스트

```js
toast('설치 완료 — 새로 열린 앱 창에서는 창 전체가 채팅방이 됩니다');
```

설치해도 **지금 보고 있는 탭은 계속 탭**이다. 창 모드는 새로 뜬 앱 창에서만 보인다.
이걸 말해주지 않으면 "설치했는데 왜 그대로냐"는 오해가 생긴다.

---

## 손댄 곳

| 파일 | 내용 |
|---|---|
| `vela-boardroom-prototype.html` | 창 모드 CSS 블록 · 좁은 창 대응 · `bindWindowMode()` · 설정 안내 2줄 · 버전 2.7.1 |
| `vela-boardroom-sw.js` | 스탬프가 `BUILD_ID` 갱신 |
| `velchat-v2.7.1-notes.md` | 이 문서 |

`vela-boardroom-manifest.json` 은 건드리지 않았다.
이미 `"display": "standalone"` 이라 미디어 쿼리가 그대로 걸린다.
`window-controls-overlay` 를 `display_override` 에 넣으면 타이틀바가 사라지는데,
그러면 창을 끌 드래그 영역을 헤더에 직접 만들어야 한다 — 다음 버전의 일이다.

---

## 확인한 것 / 못 한 것

**정적 검증** — `<style>` 블록 중괄호 균형(깊이 0), 새 변수 7개 각각 정의 3회(기본·미디어·body 클래스)/사용 1회,
`.app-shell { max-width: var(--shell-max) }` 가 기존 `var(--shell-w)` 규칙보다 뒤에 위치,
`.pc-only` 좁은화면 규칙이 `.only-browser` 보다 뒤에 위치 — 모두 통과.

**브라우저 실측은 못 했다.** 이 세션에서 Chrome 확장이 연결되지 않아
실제 설치 창을 띄워 320px 로 줄여보는 확인은 하지 못했다. 다음 순서로 눈으로 확인할 것:

1. `chrome://apps` 에서 벨챗 실행 → 좌우 배경 여백 없이 창이 꽉 차는지
2. 그 창을 320px 까지 좁히기 → 헤더가 한 줄로 남는지, 입력독 버튼이 안 밀려나는지
3. 같은 파일을 일반 탭에서 열기 → 중앙 카드형이 그대로인지 (두 모드 공존)
4. `설정 → 일반` 상단 안내가 모드에 따라 다른 문장인지
5. `설정 → 테마` 에서 창 모드일 때 "채팅창 너비"가 사라졌는지
