# 벨챗 v2.5.0 — 상세 변경 노트

> 2026-08-14 · 대상 파일: `vela-boardroom-prototype.html` (단일 파일 앱)
> 이전 버전: v2.4.0 (새 이름·아이콘 + 밝은 UI + 커스터마이징 + 대화방 목록)

화면을 대화에 몰아주고, 크기를 사용자가 직접 맞추게 하는 버전이다.

---

## 1. 몰입 모드 — 상단 정보 접기

### 무엇을 접나
접히는 것: **버전 스트립** · **방 제목 줄**(저장/재생/내보내기/새대화 버튼 포함) · **멤버 목록**
남는 것: **작은 헤더**(벨챗 로고 + 방 제목 한 줄) + **대화창** + **입력독**

```css
body.chrome-collapsed .issue-strip,
body.chrome-collapsed .chat-header,
body.chrome-collapsed .chat-participants { display: none; }
body.chrome-collapsed.chat-only main { padding-top: 8px; }
```

**실측: 대화창 높이 461px → 583px (+122px, +26%)**

### 헤더가 곧 토글
`.brand`(로고 + 벨챗 + 방 제목)를 `<button id="brandToggle">` 으로 바꿨다.
탭하면 접히고, 다시 탭하면 펼쳐진다. 오른쪽 셰브론(⌄)이 접힘 상태에 따라 90° 회전한다.

- 기존에 로고가 `<a href="...">` 라 탭하면 앱이 새로고침됐다 → `<span>` 으로 바꿔
  탭이 토글로만 동작하게 했다.
- `aria-expanded` 를 상태에 맞춰 갱신한다.
- 접히면 방 제목이 헤더의 주인공이 된다 (`flex:1`, 굵게, 색 진하게).

### 읽기를 방해하지 않는다
**접힘/펼침은 오직 헤더 탭으로만 바뀐다.** 스크롤 이벤트에는 아무것도 걸지 않았다.
위로 올려 과거를 읽어도 절대 펼쳐지지 않는다.

> 실측: 접힌 상태에서 휠 이벤트 + `scrollTop = 0` 을 두 번 반복해도
> `chromeCollapsed === true` 유지, 방 제목 줄은 계속 숨김.

### 자동 접힘 (한 번만)
```js
function autoCollapseOnFirstMessage() {
  if (state.chromeCollapsed) return;
  const real = (state.messages || []).filter(m => m.type !== 'typing');
  if (real.length !== 1) return;   // 방이 비어 있다가 첫 메시지가 들어간 순간에만
  applyChrome(true);
}
```

`sendFollowup()` 에서 사용자 메시지를 붙인 직후 호출한다.
**두 번째 메시지부터는 사용자의 펼침 선택을 덮지 않는다** — 실측 확인.

### 접었다 펼 때 스크롤 유지
대화창 높이가 122px 바뀌므로, 바닥에 있던 사람은 계속 바닥에 있어야 한다.

```js
const wasAtBottom = isChatAtBottom();   // 토글 전에 먼저 잰다
... 클래스 토글 ...
if (wasAtBottom) requestAnimationFrame(() => scrollChatToBottom(false));
```

### 저장
`localStorage['vela.boardroom.chromeCollapsed']`. 앱을 다시 열면 그 상태로 시작한다.

---

## 2. 글자 크기 조절 (80~140%, 5% 단위)

설정 → **테마** 탭 상단.

### 배율 방식
`--fs-scale` 하나로 관련 글자를 전부 비례 조정한다.

```css
:root { --fs-scale: 1; }
.msg-persona-bubble { font-size: calc(14.5px * var(--fs-scale)); }
.msg-user-bubble    { font-size: calc(14.5px * var(--fs-scale)); }
.msg-name           { font-size: calc(13px   * var(--fs-scale)); }
.msg-tag            { font-size: calc(9px    * var(--fs-scale)); }
.msg-system-chip    { font-size: calc(11px   * var(--fs-scale)); }
.msg-avatar         { font-size: calc(16px * var(--fs-scale));
                      width:  calc(32px * var(--fs-scale));
                      height: calc(32px * var(--fs-scale)); }
```

대상: 말풍선 본문(상대·내), 이름, 태그, 시스템 칩(시간·입퇴장 표기), 링크, 읽기 버튼,
사진 정리 안내, 빈 방 안내. **아바타도 함께 커진다** — 글자만 커지면 균형이 깨진다.

**레이아웃 요소(입력창·전송 버튼·아이콘 버튼)는 일부러 제외했다.**
같이 키우면 입력독이 부풀어 대화창을 잡아먹는다.

> 실측 (80% / 100% / 140%)
> 말풍선 11.6 / 14.5 / 20.3px · 이름 10.4 / 13.0 / 18.2px ·
> 태그 7.2 / 9.0 / 12.6px · 아바타 25.6 / 32.0 / 44.8px
> 입력창 14.5px 고정 · 전송 버튼 40px 고정 ✓

### 미리보기
슬라이더 바로 아래에 **실제 말풍선과 같은 모양**의 미리보기를 뒀다
(흰 배경, 같은 라운드·그림자, 이름 + 본문). `--fs-scale` 을 그대로 쓰므로
슬라이더를 움직이면 즉시 같이 변한다.

### 실시간 · 저장 · 클램프
- `input` 이벤트로 즉시 반영 (드래그 중에도)
- `localStorage['vela.boardroom.fontScale']` 저장, 재실행 시 복원
- `clampNum()` 으로 80~140 밖의 값은 잘라낸다 (실측: 999 → 140, 10 → 80)

---

## 3. PC 채팅창 너비 조절 (380~720px)

v2.4 에서 480px 고정이던 것을 슬라이더로 바꿨다.

```css
:root { --shell-w: 480px; }
.app-shell { max-width: var(--shell-w, 480px); }
```

- 범위 380~720px, 10px 단위
- 실시간 반영, `localStorage['vela.boardroom.shellWidth']` 저장
- 폭을 바꿔도 **중앙 정렬이 유지된다** (실측 확인)
- **모바일에서는 컨트롤 자체를 숨긴다** — `.pc-only { display: none }` (≤559px).
  모바일은 어차피 화면 폭을 꽉 쓰므로 조절할 게 없다

---

## 4. 검증

### 검증 환경 메모
작업 도중 Chrome 확장(claude-in-chrome) 연결이 끊겼다. 그래서 **Chrome 을 헤드리스로
띄우고 DevTools 프로토콜로 직접 붙는 하네스**를 만들어 검증했다
(Node 22+ 내장 WebSocket 사용, 외부 의존성 없음). 실제 브라우저 렌더링 기준이라
검증 강도는 동일하다. 스크린샷도 `Page.captureScreenshot` 으로 받았다.

### 몰입 모드
- 펼침 → 접힘: 대화창 461 → 583px (+122px), 스트립·제목줄·멤버목록 전부 숨김
- 접힘 상태에서도 헤더(로고+방 제목)와 입력독은 그대로 보임
- 탭 → 접힘 → 다시 탭 → 펼침, `aria-expanded` 와 저장값 동기화
- **위로 스크롤(휠 + scrollTop=0) 두 번 반복해도 펼쳐지지 않음**
- 첫 메시지에서 자동 접힘, 두 번째 메시지에서는 사용자의 펼침 선택 유지

### 크기 조절
- 글자 80/100/140% 비례 확대, 레이아웃 요소 불변, 라벨·슬라이더·저장 동기화
- 실시간 `input` 반영 (125% 즉시 적용 확인), 상·하한 클램프
- 너비 380/600/720px 정확히 반영, 중앙 정렬 유지, 실시간·저장 동작

### 회귀 (v2.1~v2.4 전부 유지)
- 입력독 바닥 고정 · 메시지 영역만 스크롤 ✓
- 스크롤 정책: 위로 읽는 중 강제 스크롤 금지 + 배지 ✓
- 내 메시지 강제 하강: 부드러운 스크롤이 2207 → 877(300ms) → **0(1s)** 로 실제 도달 확인
  (이전 버전 테스트에서 gap 이 남아 보이던 건 애니메이션 중간값을 찍었기 때문)
- 언어 가드(단어·문장·정상), 테마 전환(미드나잇), 사진 첨부 ✓
- 테마를 바꿔도 글자 배율이 유지됨 ✓
- 콘솔 에러 0건

---

## 변경 파일

- `vela-boardroom-prototype.html` — 전부 여기
- `vela-boardroom-sw.js` — 스탬프가 BUILD_ID 갱신
- `velchat-v2.5.0-notes.md` — 이 문서

## 유지보수 메모

- **접히는 대상 추가/제거** = `body.chrome-collapsed` 선택자 목록 한 줄
- **글자 크기 범위** = `SIZE_RULES.fontMin/fontMax/fontStep` + `<input>` 의 min/max/step
- **너비 범위** = `SIZE_RULES.widthMin/widthMax/widthStep` (동일)
- **새로 추가한 글자 요소를 배율에 태우려면** `calc(Npx * var(--fs-scale))` 로 적으면 된다.
  단 레이아웃을 밀어내는 요소(버튼·입력창)는 태우지 말 것
- 자동 접힘은 `autoCollapseOnFirstMessage()` 한 곳에서만 일어난다.
  조건을 바꾸고 싶으면 여기만 고치면 된다
