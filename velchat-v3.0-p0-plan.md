# 벨챗 v3.0-P0 계획서 — "LLM이 죽어도 앱은 산다"

작성일 2026-08-17 · 대상 `vela-boardroom-prototype.html`
**상태: 계획만. 승인 전까지 코드 변경 없음.**

2차 외부 리뷰 결론에 동의한다. 다만 **RPD는 아직 가설**이고, 증거를 만드는 게 먼저다.
그리고 degraded mode는 "예외 처리"가 아니라 **v3.0의 기본 동작 중 하나**로 설계한다.

---

## 0. 조사 결과 — 그리고 계획을 바꾼 제약 하나

### 429를 RPM/RPD로 나눌 수 있는가? provider마다 다르다

| provider | 판별 신호 | 브라우저에서 읽히나 | 확신도 |
|---|---|---|---|
| **Gemini** | 본문 `error.details[]` 의 `QuotaFailure.violations[].quotaId` | ✅ 본문이라 그대로 읽힌다 | **확정** |
| **Groq** | `x-ratelimit-remaining-requests` 등 헤더 | ❌ **읽을 수 없다** (아래) | 추정 |
| **Anthropic** | `anthropic-ratelimit-*` 헤더 | ❌ 읽을 수 없다 | 추정 |

Gemini의 `quotaId` 는 이름 자체가 답을 준다:

```
GenerateRequestsPerMinutePerProjectPerModel-FreeTier   → RPM
GenerateRequestsPerDayPerProjectPerModel-FreeTier      → RPD  (quotaValue 로 한도까지 알려준다)
GenerateContentInputTokensPerModelPerMinute-FreeTier   → TPM
```

### ⚠ 제약: Groq·Anthropic의 rate-limit 헤더는 브라우저에서 못 읽는다

프리플라이트를 실측했다:

```
Groq      → access-control-allow-origin: *
             access-control-expose-headers: (없음)
Anthropic → access-control-expose-headers: (없음)
```

`Access-Control-Expose-Headers` 가 없으면 JS의 `res.headers.get()` 은
CORS 안전목록 밖의 헤더를 **전부 null 로 돌려준다.** `retry-after` 조차 못 읽는다.

→ **이 앱이 브라우저 단일 파일인 한, Groq·Anthropic의 RPD/RPM은 헤더로 확정할 수 없다.**
(참고: v2.9.2에서 넣은 `parseRetryAfterMs` 의 헤더 분기가 사실상 죽은 코드였다는 뜻이기도 하다.
본문 문자열 파싱만 실제로 동작하고 있었다.)

### 그래서 이렇게 한다 — 확정과 추정을 섞되, 섞였다는 걸 표시한다

- **Gemini**: 본문 `quotaId` 로 `429_RPD` / `429_RPM` / `429_TPM` **확정**
- **Groq**: 본문 메시지 문자열로 추정 — Groq은 429 본문에
  `"...on requests per day (RPD): Limit 14400, Used 14400... try again in 7m30s"` 형태로 알려준다.
  `per day|RPD` → RPD, `per minute|RPM|TPM` → RPM/TPM
- **공통 보조 휴리스틱**: 본문에도 단서가 없으면 **대기 시간 길이**로 추정한다.
  `retryAfterMs >= ERROR_RULES.rpdHintMs`(기본 10분) → RPD 의심
- 확신도를 `confirmed` / `inferred` 로 함께 기록하고 **로그·대시보드에 그대로 표시**한다.
  추정을 확정처럼 보여주면 그게 v2.9.1 환율 사고와 같은 종류의 잘못이다.

---

## 1. 오류 분류 체계 (`ERROR_KINDS`)

```
429_RPM   분당 요청 한도    → 잠깐 기다리면 풀린다
429_RPD   일일 요청 한도    → 오늘은 끝났다. 기다려도 소용없다
429_TPM   분당 토큰 한도    → 잠깐 기다리면 풀린다
503       저쪽 서버 혼잡    → 짧게 한 번 더
TIMEOUT   응답 없음         → 짧게 한 번 더
NETWORK   연결 실패         → 짧게 한 번 더
AUTH      키·권한 문제      → 재시도 무의미. 사용자가 고쳐야 한다
MODEL_404 모델 이름 문제    → 재시도 무의미 (기존 구제 로직으로)
UNKNOWN   그 외
```

`classifyError(provider, status, rawBody, res)` → `{ kind, confirmed, resetAt, limit, used }`

- `resetAt` — RPD면 "내일 몇 시", RPM이면 "N초 뒤". degraded 안내에 쓴다.
  Gemini 무료 티어 RPD는 **태평양시 자정** 리셋이므로 그 기준으로 환산한다.
- 분류는 **provider·모델별로 일자별 집계**하고, 라우팅 로그 각 줄에도 표시한다.

```
✕ Groq  강지원  429
   ⛔ 429_RPD (추정) · 내일 16:00 리셋
```

---

## 2. `FACT_RULES` 오류별 차등 — 절대 규칙을 완화한다

v2.9.5는 "Fact가 있으면 무조건 1회"였다. 단순해서 좋았지만 **너무 거칠다** —
503 한 번에 설명을 포기하는 건 과하다. 오류 성격에 맞춘다.

```js
const FACT_RULES = {
  llmAttempts: 1,
  byKind: {
    '429_RPD':  { retry: 0 },                    // 기다려도 소용없다 → 즉시 숫자 표시
    'AUTH':     { retry: 0 },
    'MODEL_404':{ retry: 0 },
    '429_RPM':  { retry: 1, waitMs: 'retryAfter', maxWaitMs: 15000 },  // 짧게 한 번만
    '429_TPM':  { retry: 1, waitMs: 'retryAfter', maxWaitMs: 15000 },
    '503':      { retry: 1, waitMs: 2000 },
    'TIMEOUT':  { retry: 1, waitMs: 1500 },
    'NETWORK':  { retry: 1, waitMs: 1500 },
    'UNKNOWN':  { retry: 0 }
  }
};
```

- 폴백(다른 provider)은 **한 번만** 허용한다 — Fact가 있으니 오래 끌 이유가 없다.
- `maxWaitMs` 상한이 핵심이다. Retry-After가 7분이라고 7분을 기다리면 안 된다. 숫자는 이미 있다.

---

## 3. Degraded mode — LLM이 전멸해도 앱은 응답한다

### 세 갈래

| 상황 | 응답 |
|---|---|
| Fact 턴 + LLM 전멸 | **숫자 카드** (v2.9.4 구현 유지) |
| 일반 대화 턴 + LLM 전멸 | **시스템 안내 1회** — 페르소나 말풍선 아님 |
| 회복 | 자동으로 정상 복귀 (별도 조작 없음) |

### 안내 문구 — 정직하게, 리셋 시점까지

```
지금 AI 응답이 어려워요.
무료 사용량을 다 썼습니다 · 내일 오후 4시쯤 다시 열려요
```

```
지금 AI 응답이 어려워요.
잠시 몰렸습니다 · 약 40초 뒤 다시 시도해보세요
```

- 확신도가 `inferred` 면 단정하지 않는다: "무료 사용량을 다 쓴 것 같아요".
- **개발자 용어 금지 규칙(v2.9.2)을 그대로 적용한다** — 429·RPD·API 같은 말을 쓰지 않는다.

### 도배 방지

```js
const DEGRADE_STATE = { kind, provider, since, resetAt, noticeShownAt };
```

- **같은 `kind` + 같은 `resetAt` 구간에서는 안내를 한 번만** 낸다.
- 상태가 바뀌거나(RPM→RPD), 리셋 시각을 지나면 다시 낼 수 있다.
- 최소 간격 `DEGRADE_RULES.noticeGapMs`(기본 3분)도 함께 건다.
- 성공 응답이 하나라도 오면 상태를 즉시 해제하고, **"다시 연결됐어요" 안내는 내지 않는다** —
  정상 복귀는 답이 오는 것으로 이미 드러난다. 그 자체가 알림이면 그것도 도배다.

### 입력창은 막지 않는다

degraded 중에도 사용자는 계속 쓸 수 있어야 한다. Fact 질문은 여전히 답이 나가고,
LLM이 회복되면 다음 메시지부터 정상 동작한다.

---

## 4. Fact 캐시 + Freshness Policy

### TTL은 데이터 성격에 맞춘다 (이미 소스별로 분리돼 있고, 값만 조정)

| 소스 | 현재 | 변경 | 근거 |
|---|---|---|---|
| 환율(fx) | 30분 | **6시간** | ECB 계열은 **영업일 하루 1회**(16:00 CET) 갱신. 30분 캐시는 같은 값을 반복해서 받아오는 낭비다 |
| 날씨(weather) | 10분 | **30분** | open-meteo 관측 갱신 주기가 15분 단위. 30분이면 체감 차이가 없다 |

> "모든 캐시 5분" 같은 일괄 정책을 쓰지 않는 이유가 여기 있다.
> **환율에 30분은 과하게 짧고, 날씨에 6시간은 과하게 길다.** 데이터마다 변하는 속도가 다르다.

### 오래된 캐시는 위험하지 않다 — asOf 덕분에

캐시가 6시간 된 값을 줘도 **출처줄에는 원 데이터의 `asOf`(8/14 기준)가 그대로 표시된다.**
사용자가 보는 건 "언제 기준 값인가"이고, 그건 캐시 나이와 무관하게 정확하다.
이게 v2.9.3에서 `asOf` 를 넣어둔 덕을 보는 지점이다.

### 캐시 적중 시 API 왕복 생략

이미 그렇게 동작한다(`dataCacheGet`). 여기에 측정만 추가한다.

- `CACHE_HIT_RATE` = `cacheHits / (cacheHits + dataCalls)`
- 대시보드에 노출. 적중률이 낮으면 TTL이 짧다는 신호다.

---

## 5. 폴백 의미 보호 — 경로 전수 검증 + 회귀 고정

### 불변식 (Invariant)

> **Fact-required 질문에서 Fact를 확보하지 못했다면,
> 어떤 provider·어떤 폴백 경로로도 LLM이 실시간 수치를 단정하는 출력이 나갈 수 없다.**
>
> 그리고 Fact를 확보했다면, **provider가 바뀌어도 출처와 값은 불변이다.**

### 경로 전수 (4가지 — 이것이 전부임을 코드로 확인한다)

| # | 조건 | 프롬프트에 반드시 들어가는 것 |
|---|---|---|
| A | Fact 확보 | `factDirective` — "이 숫자를 바꾸지 마라" + asOf |
| B | Fact 실패 + 검색 가능 | 검색 지시 — "검색 결과가 기억보다 우선" |
| C | Fact 실패 + 검색 불가 | **단정 금지 지시** — "아는 숫자를 현재값처럼 말하지 마라" |
| D | 전부 실패 | LLM 출력 없음 → 숫자 카드 또는 degraded 안내 |

### 회귀 테스트로 고정한다

`buildChatInstruction` 을 세 경로(A/B/C)로 호출해 **금칙/필수 문구를 문자열로 검사**한다.

```
A: factDirective 포함 && asOf 포함
B: "검색 결과가 맞다" 포함
C: "현재값처럼 말하면 절대 안 된다" 포함
A/B/C 공통: freshness 질문이면 셋 중 하나는 반드시 존재  ← 이게 불변식
```

그리고 **provider 불변성**: 같은 Fact로 A 경로를 Gemini/Groq/Anthropic 각각에 대해
생성해도 주입되는 숫자·asOf·출처가 동일한지 확인한다 (프롬프트는 provider와 무관하게 조립되므로
구조상 보장되지만, 회귀로 고정해 두면 나중에 누가 provider별 분기를 넣어도 즉시 잡힌다).

---

## 6. 유료 판단 대시보드 (📊 확장)

```
오늘 (8/17)
메시지 24 · LLM 호출 27 · 메시지당 1.13콜        (목표 1.0)
체감 실패율 4.2% (24건 중 1건)   ← 기준선 2~3%   ⚠
degraded 응답 8.3% · 데이터API 6(캐시적중 67%)

오류 분류
  429_RPD 3 (Gemini 확정 2 · Groq 추정 1)
  429_RPM 1 · 503 2 · TIMEOUT 0

RPD 상태
  Gemini flash  187/200 사용 (94%)  ← 한도는 오류 본문에서 확인된 값
  Groq gpt-oss  한도 미상 (추정)
  최근 14일 중 소진: 2일           ← 기준선 3일

전환 기준선: 14일 중 3일 소진 · 체감 실패 2~3%
```

### 지표 정의 (오해 없게 못 박는다)

- **체감 실패율** = `정상 AI 응답을 못 받은 메시지 / 전체 메시지`
  숫자 카드·degraded 안내는 "응답"이긴 하지만 **정상 AI 응답은 아니므로 실패로 센다.**
  이 지표가 사용자가 실제로 겪는 불편에 가장 가깝다.
- **degraded 응답 비율** = `degraded(숫자 카드+안내) 로 끝난 메시지 / 전체`
- **RPD 사용률** — Gemini는 오류 본문의 `quotaValue` 로 한도를 알 수 있을 때만 표시한다.
  Groq·Anthropic은 브라우저에서 한도를 못 읽으므로 **"한도 미상"** 으로 두고
  429_RPD 발생 일수만 센다. *모르는 걸 아는 척하지 않는다 — 이 앱의 규칙을 대시보드에도 적용한다.*
- **RPD 소진일 수(14일)** = 하루에 `429_RPD` 가 한 번이라도 난 날의 수

---

## 7. 구현 순서

1. `classifyError` + `ERROR_KINDS` (모든 후속 작업이 이걸 참조한다)
2. 오류 분류를 측정·라우팅 로그에 기록
3. `FACT_RULES.byKind` 차등 적용
4. Degraded mode (상태 머신 + 안내 + 도배 방지)
5. 캐시 TTL 조정 + `CACHE_HIT_RATE`
6. 대시보드 확장 (기준선 표시 포함)
7. 폴백 불변식 회귀 테스트 작성
8. 회귀 → `v3.0.0-p0` 스탬프 · 커밋 · 푸시

---

## 8. 회귀 확인 목록

- v2.9.5 전부: 서킷 3경로 / `FACT_RULES` 1회 / 문장 21개 구멍 0 / Validator 5케이스
- 5인 라우팅·아카이브(정민철)·TTS 7종
- 신규: 오류 분류 8종, degraded 안내 1회만, 캐시 적중 시 왕복 생략, 불변식 A/B/C
- 문법 검사

---

## 9. 리스크

| 리스크 | 대응 |
|---|---|
| **Groq·Anthropic RPD를 확정 못 함** | 추정으로 표시하고 `inferred` 를 화면에 명시. 확정은 Gemini만 |
| 추정 오분류로 잘못된 안내 | `inferred` 면 "~인 것 같아요" 로 단정 회피 |
| degraded 안내가 성가심 | 같은 상태 1회 + 최소 간격 3분 + 회복 안내 없음 |
| 캐시 6시간이 길다는 인상 | `asOf` 가 항상 표시되므로 사용자는 기준 시점을 정확히 안다 |
| 체감 실패율 정의 논쟁 | 대시보드에 정의를 한 줄로 함께 표시 |
| 대시보드 저장 증가 | 오류 분류는 8칸 카운터. 하루 +50바이트 수준 |

---

## 부록: v2.9.2의 죽은 코드 하나

`parseRetryAfterMs` 의 `res.headers.get('retry-after')` 분기는 **브라우저에서 항상 null 이다**
(Groq·Anthropic이 `Access-Control-Expose-Headers` 를 주지 않으므로).
실제로 동작한 건 본문 문자열 파싱뿐이었다.

지우지는 않는다 — 나중에 provider가 헤더를 열어주면 그때 살아난다.
대신 **주석으로 "지금은 안 읽힌다"를 명시**해서, 다음 사람이 이 분기를 믿고 설계하지 않게 한다.

---

## 10. 코드 대조 결과 (계획 확정 전 실측 · 2026-08-18)

계획서의 전제를 실제 코드에서 확인했다. 어긋난 곳은 없고, **구현 시 주의할 지점 4개**를 추가한다.

- `DATA_SOURCES.fx.ttlMs = 30분`(5430줄) · `weather.ttlMs = 10분`(5452줄) — 4장 조정 대상 그대로.
- `FACT_RULES = { llmAttempts:1, waitOnQuota:false }`(5505줄) — 2장에서 `byKind` 를 얹는다.
  기존 두 필드는 **기본값으로 남긴다**(`byKind` 에 없는 kind는 현행 동작 유지).
- `parseRetryAfterMs`(10426줄)의 헤더 분기 확인 — 부록 그대로. 주석만 추가.
- `DEGRADE_RULES`(5523줄)는 **이미 존재한다**(v2.8.3 우아한 축소). 3장의 도배 방지 설정은
  같은 객체에 `notice*` 필드로 얹는다. 새 객체를 만들면 이름이 겹쳐 헷갈린다.

### 측정 스키마 — 하위 호환이 필요하다

`metricDay()`(4356줄)는 **새 날짜에만** 기본 객체를 만든다. 이미 저장된 14일치에는 신규 필드가 없다.
`metricBump` 은 `(d[field]||0)+1` 이라 안전하지만, **대시보드 렌더는 `undefined` 를 견뎌야 한다**
(`d.cacheHits ?? 0` 형태로 읽는다). 마이그레이션 코드는 넣지 않는다 — 14일이면 자연히 교체된다.

`metricBump` 은 평평한 카운터라 provider·kind별 집계를 못 담는다. 중첩 카운터를 하나 더 만든다:

```js
function metricBump2(field, k1, k2) {   // d[field][k1][k2]++
  // 예: metricBump2('errors', 'gemini:flash', '429_RPD')
}
```

일자별 객체에 추가되는 것: `errors{}`(provider:model → kind → n), `cacheHits`,
`degradedMsgs`, `unservedMsgs`(체감 실패), `rpdHit`(그날 429_RPD 있었으면 1), `rpdLimit{}`.
하루 +100~200바이트 수준. `METRICS.keepDays = 14` 그대로면 저장 부담은 무시할 만하다.

### 버전 스탬프 대상 (7장 8번)

`vela-boardroom-sw.js:18` `APP_VERSION` · `prototype.html:3733` `#versionTag` ·
`prototype.html:4652` `version:` — **세 곳이 같이 바뀌어야 한다.** 하나만 바꾸면
서비스워커 캐시가 이전 버전을 붙들고 있어 배포가 반영되지 않는다.
