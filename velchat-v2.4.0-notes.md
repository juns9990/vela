# 벨챗 v2.4.0 — 상세 변경 노트

> 2026-08-14 · 대상 파일: `vela-boardroom-prototype.html` (단일 파일 앱)
> 이전 버전: Vela Compass v2.3.1

이름·아이콘·UI를 전면 교체한 버전이다. **엔진(라우팅·유머·언어 가드·사진·스크롤)은
그대로 두고 껍데기만 갈아끼웠다.**

---

## ⚠️ 먼저 확인할 것 — 아이콘은 임시본이다

작업 지시에 있던 두 파일이 폴더에 없었다. 사용자 홈(`Desktop`/`Downloads`/
`Documents`/`Pictures`) 3단계까지 찾아봤지만 없었다.

- `velchat-icon-192.png` / `velchat-icon-512.png` / `velchat-icon-maskable-512.png`
- `compass-ui-preview.html`

**아이콘**: 앱이 설치 가능한 상태로 굴러가야 하므로, 지정된 파일명 그대로
**임시 아이콘을 생성해 넣었다.** 코랄 그라데이션(#fb7185 → #f97316) 라운드 사각형에
흰 말풍선 + 코랄 점 3개. 4배 슈퍼샘플링으로 가장자리를 부드럽게 처리했다.

> 진짜 아이콘이 따로 있다면 **같은 파일명으로 덮어쓰고 `node vela-boardroom-stamp.js`
> 만 다시 돌리면 된다.** 매니페스트·서비스워커·HTML 링크가 이미 그 이름을 보고 있고,
> BUILD_ID 는 파일 내용 해시라 자동으로 갱신된다.

**미리보기 파일**: 없어도 지시문에 디자인이 충분히 서술돼 있어서
(그라데이션 배경 + 블러 빛망울, 반투명 유리 헤더·입력독, 파스텔 아바타,
흰 말풍선 + 그라데이션 내 말풍선, 둥근 모서리) 그 명세대로 구현했다.
실제 시안과 세부가 다르면 알려주면 맞춘다.

---

## 1. 이름 교체 — "벨챗"

| 위치 | 값 |
|---|---|
| `<title>` | 벨챗 — 아이디어 단톡방 |
| manifest `name` / `short_name` | 벨챗 / 벨챗 |
| 헤더 | 코랄 말풍선 마크 + **벨챗** + 현재 방 이름 |
| iOS `apple-mobile-web-app-title` | 벨챗 |
| 콜로폰 | MADE BY JUNS · 벨챗 · v2.4.0 |
| PWA 바로가기 | 새 대화 / 음성으로 말하기 / 대화방 목록 / 이어서 대화 |

**`manifest.id` 는 `/vela/vela-compass` 그대로 두었다.** PWA 는 `id` 로 앱을 식별하므로,
바꾸면 기존 설치 사용자에게 별개 앱으로 잡힌다. 유지하면 이름만 자연스럽게 갱신된다.

---

## 2. 아이콘 교체

- `velchat-icon-192.png` (192, purpose `any`)
- `velchat-icon-512.png` (512, purpose `any`)
- `velchat-icon-maskable-512.png` (512, purpose **`maskable`** — 배경이 캔버스를 꽉 채우고
  내용은 안전영역 안에 들어가도록 별도 렌더)
- `velchat-icon-180.png` (iOS `apple-touch-icon`)

같이 손봐야 했던 곳:

- **서비스워커** `isBoardroomAsset()` 이 경로에 `vela-boardroom` 이 있는지로 앱 셸을
  판별한다. 새 아이콘은 `velchat-*` 이라 그대로 두면 캐시 대상에서 빠진다
  → `velchat-icon` 도 앱 셸로 인식하도록 추가. `BOARDROOM_ASSETS` 목록도 교체.
- **스탬프** `SHELL_FOR_HASH` 목록도 새 파일명으로 교체 (BUILD_ID 계산 입력).

---

## 3. 새 UI 골격

### 셸 구조
`masthead` + `issue-strip` + `main` 을 `.app-shell` 로 감쌌다. 모달·콜로폰은 바깥에 둔다.

```
body.chat-only (무대: 그라데이션 배경, flex row, 중앙 정렬)
└ .app-shell (카드: max-width 480px, overflow hidden)
  ├ .orb ×3          블러 빛망울 (filter: blur(58px))
  ├ header.masthead  유리 (backdrop-filter: blur(18px) saturate(150%))
  ├ .issue-strip     얇은 상태 줄
  ├ main
  │ └ .chat-screen
  │   ├ .chat-header / .chat-participants
  │   ├ .chat-messages   ★ 여기만 스크롤
  │   └ .chat-dock       유리 입력독 (하단 고정)
  └ ::before          배경 사진 레이어
```

> **함정 하나**: `body.chat-only` 는 v2.2 에서 `flex-direction: column` 이었다.
> 새 규칙에 `justify-content: center` 만 넣었더니 세로 중앙 정렬이 되면서
> 카드가 왼쪽에 붙었다. `flex-direction: row` 를 명시해 되돌렸다.
> (실측으로 잡았다 — 처음엔 `중앙정렬: false` 로 나왔다)

### 시각 요소
- **그라데이션 배경**: body 에 radial-gradient 2겹 + `--bg-far`
- **블러 빛망울**: 셸 안에 절대배치 원 3개. 셸이 `overflow:hidden` 이라 카드 밖으로 안 샌다
- **유리 헤더·입력독**: `backdrop-filter: blur(18px) saturate(150%)` + 반투명 배경 + 1px 테두리
- **흰 말풍선**: 상대 발언은 `--bubble`(흰색) + `box-shadow`, 왼쪽 컬러 보더 제거
- **그라데이션 내 말풍선**: 코랄 `linear-gradient(135deg, #fb7185, #f97316)` + 흰 글자
- **파스텔 아바타**: 페르소나 색을 22% 로 깔고 글자는 원색, 안쪽 링 34%
- **둥근 모서리**: 말풍선 20px(꼬리쪽 5px), 버튼 11~14px, 카드 24px

---

## 4. 테마 시스템 — 7종

`THEMES` 배열이 CSS 변수 묶음을 들고 있고 `applyTheme()` 이 `:root` 에 꽂는다.

☁️ 스카이 브리즈(기본) / 🍑 피치 크림 / 🌿 민트 소다 / 💜 라벤더 /
🌸 벚꽃 / 🍋 레몬 크림 / 🌙 미드나잇(기존 벨라 다크 계승)

### 핵심 설계 — 기존 변수 이름을 그대로 덮어쓴다
2,000줄 넘는 기존 CSS 를 다시 쓰지 않기 위해, `applyTheme()` 이 **새 토큰과 기존
토큰을 함께** 세팅한다.

```js
'--bg', '--bg-elev', '--bg-card', '--line', '--line-soft',
'--text', '--text-dim', '--text-faint', '--cyan'   ← 기존 이름 (예전 규칙이 전부 살아난다)
'--bg-far', '--orb-1..3', '--glass', '--glass-line',
'--bubble', '--bubble-text', '--shadow'            ← 새 이름
```

덕분에 예전에 작성된 규칙(모달·칩·버튼·다이어그램 등)까지 테마 전환 한 번에 다시 칠해진다.

### 내 말풍선은 테마를 타지 않는다
`--mine-grad` 는 `:root` 에 고정이고 테마 vars 에 없다.
**앱 아이콘과 같은 코랄이 전 테마 공통 정체성**이라 일부러 뺐다.

### 깜빡임 방지
메인 스크립트는 문서 맨 끝에 있어서 거기서 칠하면 기본 테마가 한 번 번쩍인다.
`<head>` 에 8줄짜리 부트 스크립트를 넣어, `applyTheme()` 이 저장해둔
**해석된 변수 묶음(`themeBoot`)** 을 첫 페인트 전에 꽂는다.

### 배경 사진
- 사진 첨부와 **같은 압축 경로**(`compressImage`, 최대 1280px JPEG)를 재사용
- 실측 3.4MB PNG → **17KB** 저장
- 밝기 슬라이더(10~100%), 사진 있으면 빛망울을 자동으로 흐리게(0.35)
- 저장 실패(용량 초과) 시 토스트로 안내하고 적용하지 않는다

---

## 5. 반응형

- **모바일**: 셸이 화면 폭을 꽉 채운다. 모서리 각짐, 상하 여백 없음
- **PC (≥560px)**: `max-width: 480px` 중앙 카드. `border-radius: 24px`,
  이중 그림자, 상하 22px 여백 → 좌우로 그라데이션 배경이 그대로 보인다
- 안전영역: 헤더는 `env(safe-area-inset-top)`, 입력독은 `env(safe-area-inset-bottom)`

---

## 6. 아바타 변경

설정 → **아바타** 탭. 페르소나(전문가 포함)마다:

- **내장 이모지 24종** — 🎨 ✏️ 💡 🔥 ✨ 🌈 / 🛠️ ⚙️ 🔧 📐 🧱 🚀 /
  📊 💰 📈 🧮 🎯 ⚖️ / 🧑‍🍳 🧑‍🔬 🧑‍💻 🦊 🐻 🐼
- **사진 업로드** — `compressAvatar()` 가 **가운데 정사각으로 크롭** 후 128px JPEG(품질 0.82).
  실측 800×400 입력 → 128×128 정사각 1KB. 표시는 CSS `border-radius: 50%` 로 원형
- **초기화** — 지우면 이름 첫 글자 + 파스텔 배경으로 돌아간다

저장은 `localStorage['vela.boardroom.avatars']`, 형태는 `{personaId: {type, value}}`.
변경 시 편집기·참여자 바·대화 내용을 함께 다시 그린다.

---

## 7. 대화방 목록 (카톡식)

헤더의 **≡ 버튼**으로 진입. `[방 아바타] 방 이름 · 마지막 메시지 · 날짜`.

- **탭하면 이어서** — 기존 `loadSession()` 재사용
- **삭제** — 행 우측 × (모바일에선 항상 보이고, PC 는 hover 시)
- **정렬** — 최근 수정순

### 기존 데이터 그대로 표시
`sessionPreview()` 가 형식별로 마지막 메시지를 캐낸다:

1. 새 형식 `messages` 역순 탐색 (사진만 있으면 "사진 N장")
2. v1.x `followups` 의 마지막 답변 → 없으면 질문
3. `minutes` / `summary` (마크다운 기호 제거)
4. `facts` 의 첫 항목

v2 가 아닌 세션에는 `이전 형식` 배지를 붙인다. 페르소나 이름은 **그 세션 기준**으로
푼다(`sessionPersonaName`) — 옛 세션의 전문가는 지금과 다른 사람일 수 있다.

### 날짜 (`roomDate`)
오늘 → `오전 9:44` · 어제 → `어제` · 올해 → `6월 30일` · 그 전 → `2025. 7. 10.`

---

## 8. 검증 (실제 브라우저 실측)

### 새 기능
- 이름·타이틀·매니페스트·아이콘 4종 전부 200 OK, `purpose` 정확
- 셸 480px 중앙 정렬, 그림자·24px 라운드, 빛망울 3개
- 유리 효과: 헤더·입력독 모두 `blur(18px) saturate(1.5)` 적용 확인
- **테마 7종 전환** — bg/text/accent/bubble 모두 교체, `data-theme`·`colorScheme`·
  `<meta theme-color>` 동기화, 내 말풍선 코랄 고정 확인
- 테마 저장·복원 (새로고침 후 midnight 유지), 부트 캐시 19개 변수
- 아바타: 이모지 24×3, 사진 정사각 크롭 128×128, 초기화 개별 동작
- 배경 사진: 3.4MB → 17KB, 밝기 슬라이더, 지우기
- 대화방 목록: 6종 형식(신형·사진만·어제·v1 followups·v1 facts·빈 방) 전부 정상 표시,
  정렬·탭·삭제·이전 형식 배지 확인
- 모바일 풀폭 / PC 카드형 양쪽 확인
- 콘솔 에러 0건

### 회귀 (v2.1~v2.3.1 기능 전부 유지)
- 언어 가드: 단어 수준(`words`), 문장 수준(`ratio+words`), 정상 통과, 브랜드명 통과
- 문자 필터: 아랍어·키릴·한자 제거 + 로그 기록
- 페르소나: 3인 말투 블록 + 예시 대사 3개씩
- 라우팅: 무게 판정·응답자 선정
- 스크롤 정책: 위에서 읽는 중 강제 스크롤 금지 + 배지, 내 메시지 강제 하강
- 사진 첨부: 스트립·썸네일·멀티모달 이미지 블록

### 작업 중 잡은 실제 결함 2건
1. **카드가 왼쪽에 붙음** — 기존 `flex-direction: column` 이 남아 중앙 정렬이 안 됐다.
   `flex-direction: row` 명시로 해결 (실측으로 발견)
2. **입력창 텍스트 잘림** — 긴 플레이스홀더가 2줄로 접히며 높이가 모자랐다.
   `min-height: 44px` + 플레이스홀더 단축("아무 얘기나 편하게") + 자동 높이 하한 44px

---

## 변경 파일

- `vela-boardroom-prototype.html` — 앱 전체
- `vela-boardroom-manifest.json` — 이름·아이콘·색·바로가기 (id 유지)
- `vela-boardroom-sw.js` — 앱 셸 목록 + `velchat-icon` 인식, APP_VERSION
- `vela-boardroom-stamp.js` — `SHELL_FOR_HASH` 목록
- `velchat-icon-192.png` / `-512.png` / `-maskable-512.png` / `-180.png` — **신규(임시본)**
- `velchat-v2.4.0-notes.md` — 이 문서

## 유지보수 메모

- **테마 추가** = `THEMES` 배열에 항목 하나. `vars` 키는 기존과 같아야 한다
- **아바타 이모지 변경** = `AVATAR_EMOJIS` 배열
- **아바타 사진 크기·품질** = `AVATAR_RULES`
- **내 말풍선 색** = `MINE_GRADIENT` / CSS `--mine-grad` (테마 무관 공통)
- 파일명이 여전히 `vela-boardroom-*` 인 이유는 **PWA `id`·`start_url`·`scope` 가
  그 경로에 묶여 있기 때문**이다. 파일명을 바꾸면 기존 설치 사용자의 앱이 끊긴다.
  표시되는 이름만 벨챗으로 바꾸는 게 맞다.
- v2.0 회의 기능(라운드·회의록·모드)은 `FEATURES` 플래그로 여전히 꺼둔 상태다.
