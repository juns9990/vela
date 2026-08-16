# 벨챗 v2.7.2 — 모바일 키보드가 입력창을 가리던 문제 (긴급 수정)

## 결론부터

**범인은 CSS 한 줄이다.**

```css
body { min-height: 100vh; }      /* 매거진 시절 규칙 — 79번째 줄 근처 */
```

이 규칙이 살아 있는 채로 v2.2 가 그 아래에 이걸 얹었다.

```css
body.chat-only {
  position: fixed;
  height: var(--app-h, 100dvh);   /* 키보드가 뜨면 syncViewport() 가 줄여준다 */
}
```

`min-height` 와 `height` 는 다른 속성이라 서로 덮어쓰지 않는다.
CSS 의 사용 높이는 **`max(min-height, height)`** 로 계산된다.
`100vh` 는 레이아웃 뷰포트 기준이라 키보드가 떠도 줄지 않는다. 그래서

```
사용 높이 = max(100vh, --app-h) = 100vh    (--app-h 가 아무리 작아져도)
```

**즉 v2.2 부터 지금까지, visualViewport 대응은 코드만 돌고 있었고
화면에는 단 1px 도 반영된 적이 없다.** 셸은 늘 100vh 높이의 고정 박스였고,
그 바닥에 붙은 입력독은 키보드 뒤로 들어가 있었다.

---

## 1. 원인 조사 — 언제 깨졌나

요청서의 가설은 "v2.5(몰입 모드)나 v2.7.1(창 모드 변수 개편)을 거치며 깨졌나"였다.
**둘 다 아니다. 처음부터 동작한 적이 없다.**

v2.2 커밋(`aaaa0cd`)의 원본을 꺼내 확인했다.

```
$ git show aaaa0cd:vela-boardroom-prototype.html | grep -n "min-height: 100vh"
80:    min-height: 100vh;
```

그리고 같은 커밋의 `body.chat-only` 블록에는 `min-height` 재설정이 없다.

```css
body.chat-only {
  position: fixed;
  left: 0; right: 0;
  top: var(--vv-top, 0px);
  height: var(--app-h, 100dvh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  overscroll-behavior: none;
}
```

이후 v2.5 · v2.6 · v2.7.0 · v2.7.1 어느 커밋도 이 블록의 높이 계산을 건드리지 않았다.
v2.7.1 이 추가한 `padding: var(--stage-pad) 0` 은 `@media (min-width: 560px)` 안이라
폰에는 아예 적용되지 않고, `* { box-sizing: border-box }` 덕에 태블릿에서도 무해하다.

**따라서 v2.7.1 은 무관하다.** 회귀가 아니라 v2.2 부터의 잠복 버그다.

### 왜 지금까지 안 걸렸나

- 데스크탑에는 소프트 키보드가 없다 — `--app-h` 가 줄어들 일 자체가 없었다.
- 폰에서도 **입력 한 줄**만 치면 커서가 화면 맨 아래 근처라 "좀 답답한데" 정도로 넘어간다.
  두 줄 이상 길어지거나 키보드가 큰 기기(한글 천지인·구글 키보드 툴바)에서 확실히 드러난다.
- v2.5 몰입 모드로 헤더를 접으면 대화 영역이 아래로 더 내려와 증상이 **더 심해진다**.
  "v2.5 이후 심해졌다"는 체감은 이 때문이지, 원인은 그 전부터 있었다.

### 브라우저 탭 / 설치형 구분

| | 증상 |
|---|---|
| 안드로이드 크롬 **탭** | 발생. 게다가 주소창이 있어 `100vh` 와 실제 보이는 높이의 차이가 더 벌어진다 |
| 안드로이드 크롬 **설치형** | 발생. 주소창이 없어 평소엔 딱 맞다가, 키보드가 뜨는 순간 정확히 키보드 높이만큼 가려진다 |
| iOS Safari **탭** | 발생 + 화면이 통째로 밀려 올라가 헤더가 사라지기도 한다 |
| iOS **홈 화면 앱** | 발생. `navigator.standalone` 이라 `display-mode` 미디어 쿼리도 안 걸린다 |

설치형에서 더 확실히 보이는 이유: 탭에서는 크롬이 주소창을 접었다 폈다 하며
높이가 계속 출렁여서 "원래 그런가" 싶은데, 설치형은 크롬 UI 가 없어 기준이 고정이라
가려진 양이 정확히 키보드 높이로 드러난다.

### 두 번째 원인 — 안드로이드 크롬의 기본 동작

CSS 를 고쳐도 안드로이드에는 한 겹이 더 있다.
크롬의 기본값은 `interactive-widget=resizes-visual` 이다.
키보드가 떠도 **레이아웃 뷰포트는 그대로 두고 비주얼 뷰포트만 줄인다.**
그래서 `100vh` 도, `position: fixed` 의 기준 박스도 키보드를 "없는 것"으로 계산한다.
JS 로 매 프레임 보정할 수는 있지만, 애초에 브라우저에 알려주는 표준 방법이 있다.

---

## 2. 수정 — 세 겹

### ① CSS: `min-height` 바닥을 걷어낸다 (진짜 수정)

```css
body.chat-only {
  position: fixed;
  left: 0;
  right: 0;
  top: var(--vv-top, 0px);
  min-height: 0;                                          /* ← 이 한 줄이 전부다 */
  height: calc(var(--app-h, 100dvh) - var(--kb-lift, 0px));
  ...
}
```

`min-height: 0` 을 넣는 순간 `--app-h` 가 비로소 살아난다.
v2.2 가 짜둔 visualViewport 배관이 6개월 만에 처음으로 화면에 연결된다.

`body { min-height: 100vh }` 자체는 그대로 둔다 — 매거진 레이아웃(`FEATURES.startScreen`)이
아직 그 값을 쓰기 때문이다. 채팅 셸에서만 국소적으로 푸는 게 맞다.

### ② meta viewport: 안드로이드에 레이아웃까지 줄이라고 지시

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover,
      interactive-widget=resizes-content" />
```

`resizes-content` 는 "키보드만큼 레이아웃 뷰포트 자체를 줄여라"는 표준 값이다(크롬 108+).
이걸 켜면 `100vh` · `100dvh` · `position: fixed` 가 전부 저절로 맞는다.
iOS 사파리는 이 키를 무시하므로, 그쪽은 아래 ③ 의 JS 보정이 맡는다.
값을 모르는 브라우저는 통째로 무시하므로 넣어서 손해 볼 일은 없다.

### ③ JS: visualViewport 추적을 제대로

`syncViewport()` 를 다시 썼다.

```js
function syncViewport() {
  const vv = window.visualViewport;
  const h = vv ? vv.height : window.innerHeight;
  const top = vv ? vv.offsetTop : 0;
  const root = document.documentElement;
  root.style.setProperty('--app-h', h + 'px');
  root.style.setProperty('--vv-top', top + 'px');

  const typing = isTypingTarget(document.activeElement);
  if (!typing) restingViewportH = h;
  const open = typing && hasSoftKeyboard() && (restingViewportH - h) > KB_MIN_DROP_PX;
  if (open !== kbOpen) {
    kbOpen = open;
    document.body.classList.toggle('kb-open', open);
    if (!open) root.style.setProperty('--kb-lift', '0px');
  }

  if (root.classList.contains('chat-lock')) {
    const se = document.scrollingElement || root;
    if (se && se.scrollTop !== 0) se.scrollTop = 0;   // iOS 가 밀어올린 문서 되돌리기
  }
}
```

**키보드 판정을 "높이가 줄었다"로만 하지 않은 이유.**
그러면 데스크탑에서 입력창에 커서를 둔 채 창을 세로로 줄일 때 오탐이 난다.
그래서 세 조건을 모두 요구한다 — 입력 요소에 포커스가 있고, 소프트 키보드가 있는 기기이고
(`(hover: none) and (pointer: coarse)`), 기준선 대비 120px 이상 줄었을 것.

**기준선(`restingViewportH`)을 포커스가 없는 동안 계속 갱신**하는 게 핵심이다.
그러면 화면 회전·주소창 접힘·데스크탑 리사이즈가 저절로 반영되고,
"키보드 높이"를 하드코딩하거나 기기별로 분기할 필요가 사라진다.

**rAF 로 묶는다.** 키보드 애니메이션 동안 `resize`/`scroll` 이 초당 수십 번 온다.

```js
function scheduleViewportSync() {
  if (vvSyncRaf) return;
  vvSyncRaf = requestAnimationFrame(() => {
    vvSyncRaf = 0;
    syncViewport();
    ensureDockVisible();
    if (chatStickToBottom) scrollChatToBottom(false);   // 대화는 바닥 유지
  });
}
```

**포커스 직후 여러 번 찍는다.** iOS 는 키보드가 다 올라온 뒤에야, 그것도 한 번만
`resize` 를 주는 경우가 있다. 애니메이션 구간에 못을 박아둔다.

```js
const KB_SETTLE_MS = [0, 60, 160, 320, 550];
```

`focusin` / `focusout` 을 **document 에 한 번만** 건다. 입력창이 본문·설정 모달 등
여러 개라 요소마다 거는 것보다 안전하고, 나중에 추가되는 입력창도 자동으로 포함된다.

### ④ 마지막 안전망 — `--kb-lift`

위 세 겹이 다 통해도 독이 가려지는 기기가 있다(일부 안드로이드 서드파티 IME).
독의 아래끝과 보이는 영역의 아래끝을 **실측**해서 차이만큼 셸을 줄인다.

```js
const cur = parseFloat(root.style.getPropertyValue('--kb-lift')) || 0;
const overflow = dock.getBoundingClientRect().bottom - (vv.offsetTop + vv.height);
let next = cur + overflow;
```

셸 높이가 이미 `--kb-lift` 를 빼고 있으므로 **현재 보정치에 초과분을 더하면 한 번에 수렴한다**
(빼기만 하면 매 프레임 진동한다). 폭주 방지로 `vv.height * 0.6` 에서 자르고,
키보드가 내려가면 `0px` 으로 되돌린다. 모달이 떠 있으면 아예 계산하지 않는다 —
그때 타이핑 중인 건 독이 아니라 모달 입력칸이고, 보정해봐야 뒤 배경만 흔들린다.

### ⑤ 키보드가 떠 있는 동안의 여백 — `body.kb-open`

```css
body.chat-only.kb-open .chat-input-bar { padding-bottom: 8px; }

@media (min-width: 560px) {
  body.chat-only.kb-open { padding: 0; }
  body.chat-only.kb-open .app-shell { border-radius: 0; }
}
```

iOS 는 키보드가 뜨면 `env(safe-area-inset-bottom)` 을 0 으로 주지만,
안드로이드는 제스처바 인셋을 계속 보고한다. 그대로 두면 입력창 아래에 죽은 띠가 생기고
그만큼 글자 줄이 위로 밀린다. 태블릿·가로모드에서는 카드형 무대 여백도 같이 접는다.

### ⑥ 덤 — 모달도 보이는 영역 안으로

```css
body.chat-only .modal-backdrop {
  top: var(--vv-top, 0px);
  bottom: auto;
  height: var(--app-h, 100dvh);
}
```

`inset: 0` 은 레이아웃 뷰포트 기준이라, iOS 에서 키보드가 뜨면
설정 모달의 **API 키 입력칸**이 똑같이 키보드 뒤로 들어간다. 같은 배관을 그대로 물려준다.

---

## 3. 실기기 확인 — `?debug=kb`

설치형 PWA 는 DevTools 를 붙이기가 번거롭다. 폰에서 눈으로 확인할 수단을 넣었다.

```
vela-boardroom-prototype.html?debug=kb
```

우상단에 숫자 오버레이가 뜬다. 파라미터가 없으면 아무 것도 하지 않는다.

```
mode  window        ← tab / window (설치형인지)
vv.h  312  top 0    ← visualViewport 높이 / 오프셋
inner 732  rest 732 ← window.innerHeight / 키보드 없을 때의 기준선
body  312           ← 실제 셸 높이  ★ 이게 vv.h 와 같아야 정상
lift  0px           ← 실측 보정치
kb    OPEN
over  -4  ✓         ← 독 아래끝 − 보이는 영역 아래끝
```

**읽는 법은 `over` 한 줄이면 된다.** 0 이하 = 정상, 양수 = 그만큼 키보드에 가려진 것.
수정 전이라면 키보드를 올렸을 때 `over` 가 키보드 높이(보통 260~340)로 뜨고
`body` 가 `vv.h` 보다 그만큼 크게 나온다 — 이게 `min-height: 100vh` 의 지문이다.

### 확인 목록 — 탭/설치형 × 키보드 표시/숨김 4조합

**A. 안드로이드 크롬 — 브라우저 탭**
1. 입력창 탭 → 키보드 올라옴 → 입력독이 키보드 **바로 위**에 붙는가 (`over ≤ 0`)
2. 두세 줄 길게 입력 → 입력 중인 줄이 항상 보이는가
3. 키보드 내림 → 독이 화면 맨 아래로 복원, `lift 0px`, `kb closed`
4. 주소창을 접었다 폈다(스크롤) → `rest` 가 따라 갱신되고 오탐(`kb OPEN`)이 없는가

**B. 안드로이드 크롬 — 설치형(홈 화면 앱)**
5. 위 1~3 반복. `mode` 가 `window` 로 뜨는지 함께 확인
6. 키보드 올린 채 **가로로 회전** → 회전 후에도 `over ≤ 0`
7. 서드파티 키보드(구글 키보드 툴바/천지인)로 한 번 더 — `lift` 가 붙어도 결과가 맞으면 정상

**C. iOS 사파리 — 브라우저 탭**
8. 입력창 탭 → 헤더가 위로 사라지지 않는가 (문서 밀림 되돌리기 확인)
9. 키보드 내림 → 원래 위치로 정확히 복원, 스크롤 잔상 없음
10. 홈 인디케이터 영역에 죽은 띠가 없는가

**D. iOS 홈 화면 앱**
11. 위 8~10 반복. `mode` 가 `window` 인지 확인
       (`navigator.standalone` 경로 — v2.7.1 의 `body.pwa-window` 가 걸려야 한다)
12. **설정 모달**을 열고 API 키 입력칸 탭 → 입력칸이 키보드 위에 보이는가

**공통**
13. 키보드가 뜬 상태에서 메시지를 보내 → 대화가 바닥에 붙어 따라 내려가는가
14. 위로 올려 읽는 중에 키보드를 올려 → **강제로 바닥으로 끌려가지 않는가**
       (`chatStickToBottom` 이 false 면 건드리지 않는 정책 유지)
15. 데스크탑에서 창을 세로로 줄여 → `kb` 가 `closed` 를 유지하는가 (오탐 가드)

---

## 손댄 곳

| 파일 | 내용 |
|---|---|
| `vela-boardroom-prototype.html` | `min-height: 0` · meta viewport · `syncViewport` 재작성 · `ensureDockVisible` · `body.kb-open` · 모달 뷰포트 추적 · `?debug=kb` · 버전 2.7.2 |
| `vela-boardroom-sw.js` | 스탬프가 `BUILD_ID` 갱신 |
| `velchat-v2.7.2-notes.md` | 이 문서 |

---

## 확인한 것 / 못 한 것

**정적 검증** — `<style>` 중괄호 균형(깊이 0), `<script>` 두 블록 모두 `new Function()` 파싱 통과,
`min-height: 0` 이 `body { min-height: 100vh }` 보다 뒤이면서 특이도도 높음,
`--kb-lift` 정의/사용 짝, 신규 함수 7개 정의·참조 확인. 전부 통과.

**브라우저·실기기 확인은 못 했다.** 이 세션에서 Chrome 확장이 연결되지 않아
키보드를 실제로 올려보는 검증은 하지 못했다. 위 15개 항목이 그래서 남은 몫이다.
`?debug=kb` 의 `over` 값 하나만 봐도 1분이면 판정된다.

**남은 위험 하나** — `interactive-widget=resizes-content` 는 키보드가 뜰 때
레이아웃을 통째로 다시 계산한다. 대화가 아주 긴 방에서 키보드를 여닫을 때
한 프레임 정도 버벅일 수 있다. 실기기에서 거슬릴 정도면 이 키를 빼도 된다 —
`min-height: 0` 과 JS 보정만으로도 동작은 한다(안드로이드에서 한 겹이 얇아질 뿐이다).
