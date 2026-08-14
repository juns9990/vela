# Vela Compass v2.3.1 — 상세 변경 노트

> 2026-08-14 · 대상 파일: `vela-boardroom-prototype.html` (단일 파일 앱)
> 이전 버전: v2.3.0 (영어 혼입 차단 · 페르소나 말투 강화)

패치 하나짜리 버전이다. v2.3.0 이 놓친 **단어 수준 외국어 혼입**을 막는다.

---

## 1. 문제 — 세 겹의 방어를 전부 빠져나가는 케이스

```
"단어 kombin해서 만들면 훨씬 자연스러워요"
```

이 한 줄이 v2.3.0 의 방어를 전부 통과했다.

| 방어 | 왜 못 잡나 |
|---|---|
| `ALIEN_CHAR_RE` (문자 필터, v2.2) | `kombin` 은 전부 라틴 문자다. **허용 문자**라 지워지지 않는다. |
| 한글 비율 검사 (문장 수준, v2.3) | 이 문장의 한글 비율은 **71%**. 기준(50%)을 한참 넘는다. |
| 프롬프트 규칙 | "영어 문장 금지"라고만 했지, 단어 하나는 명시하지 않았다. |

**비율 검사는 문장이 통째로 기우는 경우만 잡는다.** 문장은 멀쩡한 한국어인데
단어가 한 개씩 섞이면 비율이 거의 안 움직여서 원리적으로 걸릴 수가 없다.
`kombin`(터키어), `mesele`(터키어), `biraz`(터키어) 같은 **영어도 아닌 라틴 표기
외국어**라 더 눈에 띈다.

→ 문장 단위가 아니라 **단어 단위**로 한 번 더 본다.

---

## 2. 단어 수준 검사

### 판정 규칙
본문에서 라틴 문자 단어를 전부 뽑아, **아래 셋 중 하나도 아니면 의심**으로 본다.

1. **전부 대문자 약어** — `API`, `MES`, `KPI`, `ERP`, `QC`
2. **허용 사전(`LATIN_WORD_ALLOW`) 등록** — 브랜드명·기술 용어·`ok`/`wifi` 같은 관용어
3. **`minWordLength` 미만** — 한 글자 (`A안`, `B급`, `e-메일`의 `e`)

URL·코드·마크다운 링크·이메일 주소 안은 **기존 제외 로직을 그대로 재사용**한다
(v2.3 의 `hangulRatio` 가 쓰던 것을 `stripNonProse()` 로 빼내 공유).

```js
function findForeignWords(text) {
  const s = stripNonProse(text);
  const re = /[A-Za-z]+/g;          // 하이픈·따옴표는 구분자로 본다
  ...
    if (isAllowedLatinWord(w)) continue;
    // 같은 단어는 한 번만 담는다
}
```

- 하이픈·아포스트로피는 **구분자**다: `e-mail` → `e` + `mail`, `Here's` → `Here` + `s`
- 중복 단어는 한 번만 기록한다 (로그·지시문이 지저분해지지 않게)

### 설정 (`LANG_GUARD` 에 추가)
```js
maxForeignWords: 0,   // 의심 단어가 이 개수를 넘으면 재생성 (0 = 하나라도 나오면)
minWordLength: 2      // 이보다 짧은 라틴 단어는 검사하지 않는다
```

---

## 3. 허용 사전 — `LATIN_WORD_ALLOW` (CONFIG)

`Set` 하나로 CONFIG 블록에 둔다. **오탐이 나오면 소문자로 한 줄 추가하면 끝난다.**

대문자 약어·한 글자·URL 내부는 이미 규칙으로 통과하므로, 사전에 담는 건
**"대소문자 섞인 고유명사"와 "소문자 관용어"** 뿐이다. 분류별로 정리해뒀다:

- **관용어** — ok, okay, wifi, email, mail, ppt, excel, tv, dm, vs, diy, faq …
- **플랫폼·서비스** — naver, kakao, coupang, baemin, toss, wadiz, smartstore, musinsa,
  google, youtube, instagram, tiktok, notion, slack, amazon, samsung, shopify, etsy …
- **제작·디자인 도구** — figma, canva, adobe, photoshop, illustrator, blender, unity,
  autocad, solidworks, fusion, rhino, sketchup, cura, procreate …
- **개발·데이터** — github, git, python, react, docker, aws, firebase, vercel, json, csv …
- **AI** — chatgpt, gpt, claude, anthropic, openai, gemini, midjourney, llm …
- **파일·포맷** — pdf, png, jpg, svg, mp4, zip, psd, stl, dxf, dwg, step, gcode …
- **소재·기술** — pla, abs, petg, tpu, resin, sla, fdm, cnc, mdf, pvc, led, oled, usb, qr …
- **단위** — cm, mm, kg, ml, hz, fps, dpi, mah, inch, oz …
- **사업 용어** — saas, b2b, d2c, mvp, roi, roas, crm, erp, mes, sku, seo, ctr, ux, cs …

의도적으로 **일반 영어 단어(one, free, size, cost …)는 넣지 않았다.** 넣으면
진짜 영어 문장이 통과해버린다.

---

## 4. 파이프라인 재사용 — 새로 만들지 않았다

방아쇠만 둘로 늘리고, **재생성 경로는 v2.3 것을 그대로 쓴다.**

```js
function checkKorean(text) {
  const ratioBad = isTooMuchEnglish(text);          // ① 문장 수준 (v2.3)
  const words = findForeignWords(text);             // ② 단어 수준 (v2.3.1)
  const wordsBad = words.length > LANG_GUARD.maxForeignWords;
  return { needsRewrite: ratioBad || wordsBad, reason, words, ratio };
}
```

`runPersonaTurn` 의 분기 조건이 `isTooMuchEnglish(...)` 에서
`checkKorean(...).needsRewrite` 로 바뀐 것이 전부다. 루프·채택 조건·로그·
실패 처리는 그대로다.

- **1회 재생성** (`LANG_GUARD.retries`)
- **개선될 때만 채택** — 판단 기준을 `isBetterKorean()` 으로 확장했다.
  의심 단어 수를 **먼저** 보고, 같으면 한글 비율로 판단한다.
  (단어 1개 → 영어 문장으로 바뀌는 악화 케이스를 실제로 걸러낸다)
- **실패하면 그대로 표시** + `gaveup` 로그. 사용자에게 빈 화면을 주지 않는다.
- 정상 답변은 추가 콜이 **0**이다.

### 재생성 지시문 — 문제 단어를 직접 짚는다
`KOREAN_REWRITE_DIRECTIVE`(상수)를 `buildKoreanRewriteDirective(check)`(함수)로 바꿨다.

- 단어 때문에 걸린 경우 첫 줄이 바뀐다:
  *"방금 네 답변에 한국어가 아닌 외국어 단어가 섞였다."*
- 그리고 **의심 단어를 목록으로 명시**한다 (최대 12개):

```
[특히 이 단어들이 문제다 — 반드시 고쳐라]
- "kombin"
이 단어들은 한국어에 없는 외국어 표기이거나, 한국어로 충분히 쓸 수 있는 말이다.
브랜드·제품·기관의 실제 이름이라면 그대로 둬도 된다. 그 외에는 전부 한국어로 옮겨라.
```

"영어 쓰지 마라"보다 "이 단어를 바꿔라"가 훨씬 잘 먹힌다.

---

## 5. 로그

`window.__compassLangLog` 항목에 두 필드를 추가했다.

- `reason` — `'ratio'` | `'words'` | `'ratio+words'`
- `foreignWords` — 의심 단어 목록

`stage` 는 **최초 방아쇠 기준**으로 접두사가 붙는다 (단어로 걸렸으면 `word_`):

- `word_detected` → `word_recovered` — 단어 때문에 걸렸고 재생성으로 해결
- `word_detected` → `word_gaveup` — 재생성해도 실패, 그대로 표시
- `detected` → `recovered` / `gaveup` — 문장 수준(비율)으로 걸린 기존 경로

```
[compass:한국어] 외국어 단어 감지 — 재생성 시도 · 한글비율 71% (한글 17 / 영문 6)
                 · 의심 단어: kombin — anthropic/claude-sonnet-4-6 · maker
```

provider·모델·페르소나가 함께 찍히므로 **어느 모델이 어떤 단어를 섞는지**
바로 확인된다.

---

## 6. 부수 수정 — 브랜드명 오탐 (비율 검사)

허용 사전을 만들고 보니, 기존 비율 검사가 정상 문장을 오판하고 있었다.

```
"Figma에서 시안 잡고 Adobe Illustrator로 넘기면 됩니다"  → 한글 비율 38% → 재생성 (오탐!)
```

브랜드명이 길어서 영문 글자 수가 부풀려진 탓이다. 허용 사전이라는 판단 근거가
생겼으니, **비율 계산에서도 허용 단어를 분모에서 뺀다.**

```js
function hangulRatio(text) {
  const s = stripNonProse(text).replace(/[A-Za-z]+/g, (w) => isAllowedLatinWord(w) ? ' ' : w);
  ...
}
```

같은 판단 기준(`isAllowedLatinWord`)을 문장 수준과 단어 수준이 **공유**하므로
두 검사가 서로 어긋날 일이 없다. 위 문장은 이제 통과한다.

---

## 7. 프롬프트 보강

`COMMON_RULES` 의 영어 섹션에 단어 수준을 명시했다.

> **단어 하나도 마찬가지다.** 문장이 한국어여도 그 안에 라틴 문자로 쓴 외국어 단어가
> 하나라도 섞이면 위반이다. "단어 kombin해서", "그 mesele는", "biraz 애매한데" 같은 식으로
> 한국어 문장에 외국어 단어를 끼워 넣지 마라.
> 영어가 아닌 언어(터키어·인도네시아어·프랑스어 등)를 라틴 문자로 적는 것도 똑같이 금지다.
> → 각각 "단어를 조합해서", "그 문제는", "좀 애매한데" 로 쓴다.

실제 관측된 오류를 그대로 예시로 넣었다 — 모델은 추상 규칙보다 반례에 반응한다.

---

## 검증 (실제 브라우저 실측)

### 판정 정확도 — 19개 케이스, 오판 0건

**차단되어야 하는 것 (6건, 전부 차단됨)**
- `단어 kombin해서 …` → `words` · 의심 `kombin` · 비율 71%
- `그 mesele는 …` → `words` · 의심 `mesele` · 비율 63%
- `biraz 애매한데 …` → `words` · 의심 `biraz` · 비율 64%
- `이거 completely 다른 …` → `ratio+words` · 비율 47%
- `Let me break this down. …` → `ratio+words` · 비율 0%
- `그 approach는 risk가 too high합니다` → `ratio+words` · 비율 24%

**통과되어야 하는 것 (13건, 전부 통과됨)**
- 순수 한국어 + 숫자 / 대문자 약어 다수(`MES ERP API QC KPI`)
- `Figma에서 … Adobe Illustrator로` (사전 + 비율 보정)
- `ChatGPT랑 Claude … Notion 연동` / `네이버 스마트스토어랑 쿠팡`
- `ok 그럼 … wifi 연결만` (관용어) / `A안이랑 B안` (한 글자)
- 맨 URL / 마크다운 링크 / 인라인 코드 / 이메일 주소 (제외 로직)
- `PLA 소재 … cm 단위` (소재·단위)
- 이모지·ㅋㅋ 섞인 서다현 말투

**앞 세 케이스의 비율이 63~71%** 라는 점이 핵심이다 — 기준(50%)을 크게 넘으므로
비율 검사만으로는 절대 못 잡는다는 게 수치로 확인된다.

### 재생성 흐름
- **복구**: 단어 감지 → 지시문에 `kombin` 명시 확인 → 한국어로 교체 →
  `word_detected` + `word_recovered`
- **포기**: 재생성도 `mesele` → 그대로 표시 + `word_gaveup` (groq/llama-3.1-8b 식별)
- **정상**: `Figma` 포함 한국어 → **호출 1회, 로그 0건** (불필요한 재생성 없음)
- **악화 방지**: 재생성이 단어 1개 → 영어 문장으로 나빠진 경우 **원본 유지** 확인

### 회귀 — 이상 없음
고정 셸 레이아웃 · 메시지 영역만 스크롤 · 문자 필터(아랍어·키릴·한자) ·
페르소나 3인 말투/예시 3개 주입 · 사진 첨부 · 멀티모달 이미지 블록 전부 정상.

---

## 변경 파일

- `vela-boardroom-prototype.html` — 전부 여기 (단일 파일 앱)
- `vela-boardroom-sw.js` — 스탬프가 BUILD_ID 갱신
- `vela-compass-v2.3.1-notes.md` — 이 문서 (신규)

## 유지보수 메모

**오탐이 나오면 `LATIN_WORD_ALLOW` 에 소문자로 한 줄 추가하면 끝난다.**
CONFIG 블록(`LANG_GUARD` 바로 아래)에 분류별로 정리돼 있다.

너무 자주 걸린다면 `LANG_GUARD.maxForeignWords` 를 1 이상으로 올려
"의심 단어가 2개 이상일 때만 재생성" 으로 완화할 수 있다. 다만 그러면
`kombin` 같은 단발 혼입은 다시 통과하므로, 사전 보강을 먼저 시도하는 편이 낫다.

새 함수 배치:
- `stripNonProse()` — 제외 구간 (문장·단어 검사 공용)
- `isAllowedLatinWord()` — 허용 판정 (문장·단어 검사 공용)
- `findForeignWords()` / `checkKorean()` / `isBetterKorean()` / `langStage()`
- `buildKoreanRewriteDirective()` — 상수에서 함수로 승격
