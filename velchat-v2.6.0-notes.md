# 벨챗 v2.6.0 — 상세 변경 노트

> 2026-08-14 · 대상 파일: `vela-boardroom-prototype.html` (단일 파일 앱)
> 이전 버전: v2.5.0 (몰입 모드 + 세밀한 크기 조절)

---

## 1. 모바일 헤더 정렬 — 원인은 예전 매거진 레이아웃

### 무엇이 문제였나
좁은 화면에서 로고·제목이 가운데 뜨고 `≡ ⚙` 이 아랫줄로 내려갔다.
헤드리스 브라우저로 390px 을 재보니 `.masthead` 의 계산값이 **`flex-direction: column`** 이었다.

범인은 v2.0 시절 매거진 레이아웃에서 온 미디어 쿼리다:

```css
@media (max-width: 480px) {
  .masthead { flex-direction: column; align-items: stretch; gap: 10px; }
  .brand    { align-items: center; justify-content: space-between; }
}
```

v2.4 에서 `body.chat-only .masthead` 에 `flex-wrap: nowrap` 은 넣었지만
**`flex-direction` 은 지정하지 않아서** 저 `column` 이 그대로 살아 있었다.
`.brand` 의 `justify-content: space-between` 도 로고와 제목을 양끝으로 밀고 있었다.

### 고친 방법
채팅 셸에서는 화면 폭과 무관하게 항상 한 줄이 되도록 명시했다.

```css
body.chat-only .masthead     { flex-direction: row; flex-wrap: nowrap; align-items: center; gap: 8px; }
body.chat-only .brand        { flex-direction: row; justify-content: flex-start; flex: 1 1 auto; min-width: 0; }
body.chat-only .masthead-meta{ justify-content: flex-end; flex-wrap: nowrap; overflow: visible; flex: 0 0 auto; }
body.chat-only .brand-room   { flex: 1 1 auto; min-width: 0; max-width: none; }
```

결과: **[로고 + 벨챗 + 방 제목 ⌄ | ≡ ⚙] 한 줄.**
방 제목은 남는 폭만큼만 쓰고 넘치면 말줄임(`…`)으로 잘린다.

### 아주 좁은 화면 (≤400px)
버튼이 제목 자리를 먹지 않도록 설치 버튼의 글자를 지우고 아이콘만 남긴다.

```css
@media (max-width: 400px) {
  body.chat-only .btn-install { padding: 0 8px !important; }
  body.chat-only .btn-install .label-short { display: none !important; }
  body.chat-only .masthead { padding-left: 10px; padding-right: 10px; gap: 6px; }
}
```

### 몰입 모드와의 연결
헤더 줄 자체가 v2.5 의 접힘 토글이다. 접거나 펼쳐도 **헤더 높이(55px)와 한 줄 배치가
그대로 유지**되는 것을 실측 확인했다. 접히면 방 제목이 굵어지며 헤더의 주인공이 된다.

> 실측 (390px / 360px 양쪽)
> `flex-direction: row` · 한 줄 ✓ · 로고 왼쪽 ✓ · 메뉴 오른쪽 ✓ · 겹침 없음 ✓
> 제목 말줄임 ✓ · 제목이 버튼 영역 침범 안 함 ✓ · 접기/펼치기 후에도 한 줄 유지 ✓

---

## 2. 웰컴 멘트 로테이션

`WELCOME_LINES` 를 CONFIG 블록에 신설했다. 방을 열 때마다 무작위로 조합한다.

### 구조
```js
const WELCOME_LINES = {
  placeholder: [ { tone, text } ... ],   // 헤더 자리 (방 제목이 아직 없을 때)
  title:       [ { tone, text } ... ],   // 빈 방 큰 제목 — {names} 는 참여자 이름으로 치환
  sub:         [ { tone, text } ... ],   // 그 아래 설명 — <b>/<br> 허용
  matchToneChance: 0.65
};
```

**멘트 추가·수정은 배열에 한 줄이면 끝난다.**

### 현재 수록
- placeholder 11개 · title 12개 · sub 15개
- tone 3종: `daily`(일상) / `gag`(아재개그) / `lead`(유도)
- **아재개그 부제 9개** — "아이디어가 배고프대요. 뭐라도 던져주세요",
  "오늘의 회의 주제: 없음. 그래서 더 좋음", "회의비 0원, 참석자 3명, 준비물 당신의 아무 말",
  "정민철은 벌써 계산기를 꺼냈고 이준호는 벌써 안 된다고 할 준비를 마쳤습니다" 등
- 일상형: "오늘은?", "아침은 드셨어요?", "점심 뭐 먹을지부터 정할까요 ㅋㅋ"
- 유도형: "요즘 제일 골치 아픈 거 하나만 툭 던져봐요"

### 세트로 어울리게
```js
function pickByTone(list, tone) {
  if (tone && Math.random() < WELCOME_LINES.matchToneChance) {
    const same = list.filter(x => x.tone === tone);
    if (same.length) return pickOne(same);
  }
  return pickOne(list);   // 나머지는 일부러 엇갈리게 (일상 제목 + 개그 부제)
}
```
제목의 tone 을 기준으로 부제·헤더 문구를 65% 확률로 맞추고, 나머지는 섞는다.
**항상 같은 톤끼리만 붙이면 금방 지루해지고, 완전 랜덤이면 따로 논다.**

### 방을 보는 동안에는 고정
`rollWelcome()` 이 뽑은 세트를 `state.welcome` 에 캐시한다. 같은 방을 보는 동안
다시 렌더돼도 문구가 바뀌지 않는다 (`rollWelcome(true)` 로만 새로 뽑는다).

> 실측: 40회 추첨에서 **조합 36종** (제목 11 / 부제 14 / 헤더 11), 톤 일치율 68%.
> `{names}` 치환 ✓ · `<b>` 렌더 ✓ · 같은 방 보는 동안 고정 ✓

---

## 3. 페르소나별 목소리 (TTS)

### 우선순위
```
수동 지정(설정)  >  자동 배정(보이스 2개 이상)  >  전역 기본 보이스
피치·속도: 수동 지정 > 페르소나 프리셋,  최종 속도 = 페르소나 속도 × 전역 읽기 속도
```

### 자동 배정
기기의 한국어 보이스가 **2개 이상이면** 페르소나마다 다른 보이스를 라운드로빈으로 배정한다.
순서를 `VOICE_PERSONA_ORDER` 로 고정해서 실행할 때마다 같은 사람이 같은 목소리를 갖는다.

```js
const VOICE_PERSONA_ORDER = ['director', 'maker', 'strategist', 'expert'];
function autoVoiceFor(personaId) {
  const ko = koreanVoices();
  if (ko.length < 2) return null;      // 하나뿐이면 피치·속도로만 구분
  return ko[Math.max(0, VOICE_PERSONA_ORDER.indexOf(personaId)) % ko.length];
}
```

### 프리셋 (보이스가 하나뿐일 때의 구분 수단)
- **서다현** pitch 1.25 / rate 1.08 — 높고 경쾌
- **이준호** pitch 0.85 / rate 0.95 — 낮고 툭툭
- **정민철** pitch 1.00 / rate 0.90 — 차분
- **전문가석** pitch 0.95 / rate 1.00

보이스가 여러 개여도 프리셋은 그대로 적용된다 — 같은 보이스가 배정된 두 사람도
피치·속도로 갈린다.

### 설정 UI
설정 → 일반 탭 → **🎭 페르소나별 목소리**

- 페르소나마다: 아바타 + 이름 + 현재 배정된 보이스 이름 + **▶ 미리듣기**
- 보이스 드롭다운(자동 배정 / 설치된 한국어 보이스 목록)
- 피치 슬라이더(0.5~2.0) · 속도 슬라이더(0.6~1.6), 값 라벨 실시간 갱신
- **목소리 초기화** 버튼
- 상단 안내가 기기 상황에 맞춰 바뀐다:
  - 0개 → "한국어 음성이 설치돼 있지 않습니다…"
  - 1개 → "1개뿐이라 피치·속도로 구분합니다…"
  - 2개+ → "한국어 음성 N개 발견 — 다른 목소리를 자동 배정했습니다"

보이스 목록은 브라우저가 비동기로 채우므로 `voiceschanged` 이벤트에서 편집기를 다시 그린다.

> 실측 (한국어 보이스 2개 환경)
> 자동 배정 ✓ (Microsoft Heami / Google 한국의) · 프리셋 피치·속도가 셋 다 다름 ✓
> 수동 지정 우선 ✓ · 전역 속도 곱(0.95×1.2=1.14) ✓ · 범위 클램프 ✓ · 초기화 ✓
> 편집기 3행 · 미리듣기·피치·속도 컨트롤 각 3개 렌더 ✓

---

## 4. 검증

### 검증 하네스 개선
v2.5 에서 만든 CDP 하네스에 두 가지 문제가 있어서 고쳤다.

1. **뷰포트가 안 먹었다** — `--window-size` 만으로는 페이지 뷰포트가 안 바뀐다
   (390 을 줬는데 `innerWidth` 가 1184). `Emulation.setDeviceMetricsOverride` 를 추가해
   실제 모바일 폭으로 테스트하게 했다. **이걸 고치고 나서야 헤더 버그가 재현됐다.**
2. **실행 간 상태가 샜다** — 고정 포트(9333)를 쓰다 보니 이전 실행의 Chrome 이
   살아 있으면 거기에 다시 붙었다. 그래서 앞선 테스트가 저장한 `chromeCollapsed=1` 이
   다음 실행에 남아 "새 프로필인데 접혀 있다"는 가짜 증상이 나왔다.
   → 실행마다 포트를 바꾸고, 테스트 전에 `localStorage` 를 비우고 재로드하도록 했다.
   (앱 결함이 아니라 하네스 결함이었음을 확인)

### 회귀 (v2.1~v2.5 전부 유지)
- 몰입 모드: 접기/펼치기, 자동 접힘, 스크롤 중 유지 ✓
- 크기 조절: 글자 80/100/125/140% + 클램프, 너비 380/450/600/720px + 중앙 정렬 ✓
- 입력독 바닥 고정 · 메시지 영역만 스크롤 ✓
- 스크롤 정책: 위로 읽는 중 강제 스크롤 금지 + 배지 ✓
- 언어 가드(단어·문장·정상), 테마 전환, 사진 첨부 ✓
- 테마를 바꿔도 글자 배율 유지 ✓
- 콘솔 에러 0건

---

## 변경 파일

- `vela-boardroom-prototype.html` — 전부 여기
- `vela-boardroom-sw.js` — 스탬프가 BUILD_ID 갱신
- `velchat-v2.6.0-notes.md` — 이 문서

## 유지보수 메모

- **웰컴 멘트 추가** = `WELCOME_LINES` 의 해당 배열에 `{ tone, text }` 한 줄.
  tone 은 `daily` / `gag` / `lead` 중 하나. 톤 섞임 정도는 `matchToneChance` 로 조절
- **목소리 프리셋 변경** = `PERSONA_VOICE_PRESETS` 의 pitch/rate
- **보이스 배정 순서** = `VOICE_PERSONA_ORDER`
- **피치·속도 범위** = `VOICE_RULES`
- 헤더는 `body.chat-only` 선택자로 예전 매거진 미디어 쿼리를 덮고 있다.
  헤더를 손볼 때 **`flex-direction` 을 반드시 명시**할 것 —
  안 그러면 좁은 화면에서 다시 세로로 쌓인다
