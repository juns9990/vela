#!/usr/bin/env node
/*!
 * velchat-regress.js — 벨챗 회귀 테스트 (v3.0.0-p0)
 * ------------------------------------------------------------------
 *   실행:  node velchat-regress.js      (리포 루트에서)
 *   의존성 없음 — Node 표준 모듈만 쓴다.
 *
 * 브라우저 단일 파일 앱이라 테스트 러너를 붙일 자리가 없다.
 * 그래서 HTML 에서 최상위 함수·상수를 이름으로 잘라내 vm 샌드박스에 올리고
 * 순수 함수만 검사한다. DOM 이 필요한 건 여기서 다루지 않는다 —
 * 그건 브라우저를 붙여서 확인한다.
 *
 * ★ 여기 고정된 것들은 "다시 깨지면 안 되는 약속" 이다.
 *   특히 5번(폴백 불변식)은 v2.9.1 환율 사고의 재발 방지장치다.
 */
const fs = require('fs');
// HTML 에서 최상위 함수/상수 선언을 이름으로 잘라온다 (회귀 테스트용)
const src = fs.readFileSync('vela-boardroom-prototype.html', 'utf8').replace(/\r\n/g, '\n');
function pull(name) {
  let i = src.indexOf('\nfunction ' + name + '(');
  if (i >= 0) {
    const end = src.indexOf('\n}\n', i);
    if (end < 0) throw new Error('end not found: ' + name);
    return src.slice(i + 1, end + 3);
  }
  for (const kw of ['const', 'let']) {
    i = src.indexOf('\n' + kw + ' ' + name + ' =');
    if (i < 0) continue;
    let end = src.indexOf('\n};\n', i);
    const semi = src.indexOf(';\n', i);
    const oneLine = src.indexOf('\n', i + 1);
    if (semi >= 0 && semi < (end < 0 ? Infinity : end) && semi < oneLine) return src.slice(i + 1, semi + 2);
    if (end < 0) throw new Error('end not found: ' + name);
    return src.slice(i + 1, end + 3);
  }
  throw new Error('not found: ' + name);
}
const vm = require('vm');

const NAMES = [
  'ERROR_RULES', 'FACT_RULES', 'DEGRADE_RULES', 'METRICS', 'MESSAGE_WEIGHTS', 'APP',
  'parseRetryAfterMs', 'isModelUnknownError', 'quotaKindFromText', 'geminiQuotaInfo',
  'classifyError', 'estimateResetAt', 'nextRpdResetAt', 'errorKindLabel',
  'factRuleFor', 'factWaitMs',
  'degradeState', 'formatResetAt', 'degradedNoticeText', 'markDegraded', 'clearDegraded', 'noteDegraded',
  'factDirective', 'buildChatInstruction',
  'renderErrorKinds', 'renderQuotaPanel'
];

const sandbox = {
  console,
  Date, Math, JSON, Intl, isFinite, parseFloat, parseInt, String, Number, Array, Object, RegExp,
  systemMessages: [],
  metrics: {},
  pushSystemMessage: (t) => { sandbox.systemMessages.push(t); return { content: t }; },
  metricBump: (f, by) => { sandbox.metrics[f] = (sandbox.metrics[f] || 0) + (by === undefined ? 1 : by); },
  metricBump2: () => {},
  escapeHtml: (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
};
vm.createContext(sandbox);
/* const 선언은 vm 전역 객체에 올라가지 않는다 — 명시적으로 꺼내 온다 */
const EXPORTS = '\nthis.__C = { ERROR_RULES, FACT_RULES, DEGRADE_RULES, METRICS, degradeState };';
vm.runInContext(NAMES.map(pull).join('\n') + EXPORTS, sandbox);

let pass = 0, fail = 0;
const T = (name, cond, extra) => {
  if (cond) { pass++; console.log('  o ' + name); }
  else { fail++; console.log('  X ' + name + (extra ? '  -> ' + extra : '')); }
};
const S = (t) => console.log('\n' + t);
const { classifyError, factRuleFor, factWaitMs, formatResetAt, buildChatInstruction,
        factDirective, noteDegraded, clearDegraded, errorKindLabel,
        renderQuotaPanel, renderErrorKinds } = sandbox;
const { FACT_RULES, DEGRADE_RULES, METRICS, degradeState } = sandbox.__C;

const noHeaders = { headers: { get: () => null } };
const htmlSrc = fs.readFileSync('vela-boardroom-prototype.html', 'utf8');

/* ---------- 1. 오류 분류 ---------- */
S('1. 오류 분류 (429 판별 · 확정/추정 구분)');

const geminiRpd = {
  error: { message: 'Quota exceeded', details: [{
    '@type': 'type.googleapis.com/google.rpc.QuotaFailure',
    violations: [{ quotaId: 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', quotaValue: '200' }]
  }] }
};
let c = classifyError('gemini', 429, 'Quota exceeded', noHeaders, geminiRpd);
T('Gemini RPD -> 429_RPD 확정', c.kind === '429_RPD' && c.confirmed === true, JSON.stringify(c));
T('Gemini RPD 한도 200 을 읽는다', c.limit === 200, String(c.limit));
T('Gemini RPD 리셋 시각을 안다', c.resetAt > Date.now(), String(c.resetAt));

const geminiRpm = { error: { message: 'q', details: [{ violations: [{ quotaId: 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier' }] }] } };
c = classifyError('gemini', 429, 'q', noHeaders, geminiRpm);
T('Gemini RPM -> 429_RPM 확정', c.kind === '429_RPM' && c.confirmed, JSON.stringify(c));

const geminiTpm = { error: { message: 'q', details: [{ violations: [{ quotaId: 'GenerateContentInputTokensPerModelPerMinute-FreeTier' }] }] } };
c = classifyError('gemini', 429, 'q', noHeaders, geminiTpm);
T('Gemini 토큰 한도 -> 429_TPM (PerMinute 에 먼저 걸리지 않는다)', c.kind === '429_TPM', c.kind);

const groqRpd = 'Rate limit reached for model `x` on requests per day (RPD): Limit 14400, Used 14400, Requested 1. Please try again in 7m30s.';
c = classifyError('groq', 429, groqRpd, noHeaders, null);
T('Groq RPD -> 429_RPD 추정', c.kind === '429_RPD' && c.confirmed === false, JSON.stringify(c));
T('Groq Limit/Used 를 읽는다', c.limit === 14400 && c.used === 14400, c.limit + '/' + c.used);
T('Groq 7m30s 를 대기시간으로 읽는다', c.retryAfterMs === 450000, String(c.retryAfterMs));

const groqRpm = 'Rate limit reached on requests per minute (RPM): Limit 30, Used 30. Please try again in 12.5s.';
c = classifyError('groq', 429, groqRpm, noHeaders, null);
T('Groq RPM -> 429_RPM 추정', c.kind === '429_RPM' && !c.confirmed, c.kind);

c = classifyError('anthropic', 429, 'rate_limit_error: too many requests', noHeaders, null);
T('단서 없는 429 + 짧은 대기 -> RPM 추정', c.kind === '429_RPM' && !c.confirmed, c.kind);

c = classifyError('anthropic', 429, 'rate limit. try again in 22m', noHeaders, null);
T('단서 없는 429 + 10분 초과 대기 -> RPD 추정', c.kind === '429_RPD' && !c.confirmed, c.kind);

T('AUTH', classifyError('groq', 401, 'invalid api key', noHeaders, null).kind === 'AUTH');
T('AUTH — Anthropic 잔액', classifyError('anthropic', 400, 'Your credit balance is too low', noHeaders, null).kind === 'AUTH');
T('MODEL_404', classifyError('groq', 404, 'model not found', noHeaders, null).kind === 'MODEL_404');
T('503', classifyError('groq', 503, 'service unavailable', noHeaders, null).kind === '503');
T('529 도 503 으로', classifyError('anthropic', 529, 'overloaded', noHeaders, null).kind === '503');
T('UNKNOWN', classifyError('groq', 418, 'teapot', noHeaders, null).kind === 'UNKNOWN');
T('추정은 라벨에 (추정) 이 붙는다', /추정/.test(errorKindLabel('429_RPD', false)) && !/추정/.test(errorKindLabel('429_RPD', true)));

/* ---------- 2. FACT_RULES 차등 ---------- */
S('2. Fact 를 쥔 상태의 오류별 차등');
T('429_RPD -> 재시도 0 (기다려도 소용없다)', factRuleFor('429_RPD').retry === 0);
T('AUTH -> 재시도 0', factRuleFor('AUTH').retry === 0);
T('MODEL_404 -> 재시도 0', factRuleFor('MODEL_404').retry === 0);
T('429_RPM -> 재시도 1', factRuleFor('429_RPM').retry === 1);
T('503 -> 재시도 1', factRuleFor('503').retry === 1);
T('규칙표에 없는 종류는 기본값(재시도 0)', factRuleFor('WHATEVER').retry === 0);
T('* Retry-After 7분이어도 15초로 자른다',
  factWaitMs(factRuleFor('429_RPM'), 450000) === 15000, String(factWaitMs(factRuleFor('429_RPM'), 450000)));
T('Retry-After 가 짧으면 그대로 따른다', factWaitMs(factRuleFor('429_RPM'), 3000) === 3000);
T('503 은 고정 대기 2초', factWaitMs(factRuleFor('503'), 999999) === 2000);

/* ---------- 3. 축소 모드 ---------- */
S('3. 축소 모드 (안내 · 도배 방지 · 자동 복귀)');
const now = Date.now();
T('40초 뒤 -> "약 40초 뒤"', /초 뒤/.test(formatResetAt(now + 40000)), formatResetAt(now + 40000));
T('20분 뒤 -> "약 20분 뒤"', /분 뒤/.test(formatResetAt(now + 20 * 60000)), formatResetAt(now + 20 * 60000));
T('모르면 빈 문자열', formatResetAt(0) === '');
/* 일일 한도 리셋 시각 — 서머타임이 있어도 정확히 태평양시 자정이어야 한다.
 * 고정 오프셋으로 계산하면 3월~11월에 한 시간씩 어긋난다. */
const pacificHour = (ts) => new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Los_Angeles', hour12: false, hour: '2-digit', minute: '2-digit'
}).format(new Date(ts));
const summer = new Date('2026-08-18T12:00:00Z').getTime();
const winter = new Date('2027-01-15T12:00:00Z').getTime();
T('여름(서머타임) 리셋 = 태평양시 자정', pacificHour(sandbox.nextRpdResetAt(summer)) === '00:00', pacificHour(sandbox.nextRpdResetAt(summer)));
T('겨울 리셋 = 태평양시 자정', pacificHour(sandbox.nextRpdResetAt(winter)) === '00:00', pacificHour(sandbox.nextRpdResetAt(winter)));
T('리셋은 항상 미래다', sandbox.nextRpdResetAt(summer) > summer && sandbox.nextRpdResetAt(winter) > winter);

const tomorrow4pm = new Date(); tomorrow4pm.setDate(tomorrow4pm.getDate() + 1); tomorrow4pm.setHours(16, 0, 0, 0);
T('내일 오후 4시 -> "내일 오후 4시쯤"', formatResetAt(tomorrow4pm.getTime()) === '내일 오후 4시쯤', formatResetAt(tomorrow4pm.getTime()));

sandbox.systemMessages.length = 0;
clearDegraded();
const rpdErr = { kind: '429_RPD', kindConfirmed: true, resetAt: tomorrow4pm.getTime() };
T('전멸 시 안내가 나간다', noteDegraded(rpdErr) === true);
const notice = sandbox.systemMessages[0];
T('안내에 리셋 시점이 들어간다', /내일 오후 4시쯤/.test(notice), notice);
T('* 개발자 용어를 쓰지 않는다', !/429|RPD|RPM|API|quota|호출|오류 코드/i.test(notice), notice);
T('확정이면 단정한다', /다 썼어요/.test(notice), notice);
T('같은 상태에서 두 번째 안내는 나가지 않는다', noteDegraded(rpdErr) === false);
T('시스템 메시지도 하나뿐', sandbox.systemMessages.length === 1, String(sandbox.systemMessages.length));
T('상태가 바뀌면 다시 낸다', noteDegraded({ kind: '503', kindConfirmed: true, resetAt: 0 }) === true);
clearDegraded();
T('성공 한 번이면 상태가 풀린다', degradeState.kind === '');
T('* 회복 안내는 내지 않는다', DEGRADE_RULES.recoveryNotice === false && sandbox.systemMessages.length === 2,
  String(sandbox.systemMessages.length));
sandbox.systemMessages.length = 0;
noteDegraded({ kind: '429_RPD', kindConfirmed: false, resetAt: 0 });
T('추정이면 단정하지 않는다 ("~것 같아요")', /것 같아요/.test(sandbox.systemMessages[0]), sandbox.systemMessages[0]);
T('리셋 시점을 모르면 시점을 말하지 않는다', !/뒤|쯤/.test(sandbox.systemMessages[0]), sandbox.systemMessages[0]);

/* ---------- 4. 캐시 정책 ---------- */
S('4. 캐시 TTL (데이터별 차등)');
T('환율 TTL = 6시간', /ttlMs: 6 \* 60 \* 60 \* 1000/.test(htmlSrc));
T('날씨 TTL = 30분', /ttlMs: 30 \* 60 \* 1000/.test(htmlSrc));
T('캐시 적중을 센다', htmlSrc.indexOf("metricBump('cacheHits')") > 0);
T('적중 시 fetch 없이 돌아간다 (return hit.fact 가 fetch 앞)',
  htmlSrc.indexOf('return hit.fact') < htmlSrc.indexOf('api.frankfurter.dev'));

/* ---------- 5. 폴백 불변식 ---------- */
S('5. 폴백 불변식 — Fact 미확보 시 실시간 수치 단정 금지');
const fx = { label: '미국 달러 1달러', display: '1,390원', asOf: '2026-08-14',
             asOfText: '8월 14일 기준', sourceName: '국제 기준환율(ECB)', kind: 'fx',
             sourceUrl: 'https://frankfurter.dev', caveat: '실거래가와 다를 수 있어요', value: 1390 };
const fresh = { category: '환율' };
const base = { weight: 'normal', order: 0, isLast: true };

// 경로 A — Fact 확보 (askPersona 가 factDirective 를 앞에 붙이는 것까지 재현)
const A = factDirective(fx) + '\n\n' + buildChatInstruction(Object.assign({}, base, { freshness: fresh, hasFact: true, webSearch: false }));
// 경로 B — Fact 실패 + 검색 가능
const B = buildChatInstruction(Object.assign({}, base, { freshness: fresh, hasFact: false, webSearch: true }));
// 경로 C — Fact 실패 + 검색 불가
const C = buildChatInstruction(Object.assign({}, base, { freshness: fresh, hasFact: false, webSearch: false }));
// 경로 C2 — 같은 턴의 두 번째 응답자 (fact 도 검색도 받지 못한다)
const C2 = buildChatInstruction(Object.assign({}, base, { order: 1, freshness: fresh, hasFact: false, webSearch: false }));

T('A: 공식 값이 프롬프트에 박힌다', A.indexOf('1,390원') >= 0);
T('A: 기준 시점이 함께 간다', A.indexOf('8월 14일 기준') >= 0);
T('A: 숫자를 바꾸지 말라는 지시', /이 숫자를 바꾸지 마라/.test(A));
T('B: 검색 결과가 기억보다 우선', /검색 결과가 맞다/.test(B));
T('B: 검색 결과가 안 왔을 때의 화법까지 준비', /확인이 잘 안 되네요/.test(B));
T('C: 아는 숫자를 현재값처럼 말하지 마라', /현재값처럼 말하면 절대 안 된다/.test(C));
T('C: 개발자 용어 금지 지시 포함', /"오류" 같은 말을 쓰면 안 된다/.test(C));
T('C2: 두 번째 응답자도 같은 보호를 받는다', /현재값처럼 말하면 절대 안 된다/.test(C2));

const guarded = (s) => /이 숫자를 바꾸지 마라/.test(s) || /검색 결과가 맞다/.test(s) || /현재값처럼 말하면 절대 안 된다/.test(s);
T('* 불변식: 신선도 턴은 A·B·C 중 반드시 하나가 걸린다', [A, B, C, C2].every(guarded));
const D = buildChatInstruction(Object.assign({}, base, { freshness: null, hasFact: false, webSearch: false }));
T('신선도 질문이 아니면 이 지시는 나가지 않는다 (오탐 방지)', !guarded(D));

/* provider 불변성.
 * ★ 프롬프트 전체를 문자열 비교하지 않는다 — 말투 한 줄(마지막에 질문을 던질지)이
 *   Math.random 으로 갈리기 때문이다. 그건 연출이고 provider 와 무관하다.
 *   지켜야 할 불변식은 "Fact 의 값·출처·기준시점이 provider 에 따라 달라지지 않는다" 이므로
 *   Fact 를 실어 나르는 부분만 정확히 비교한다. */
const perProvider = ['gemini', 'groq', 'anthropic'].map(() => factDirective(fx));
T('* provider 가 바뀌어도 Fact 의 값·출처·기준시점은 불변',
  perProvider.every(p => p === perProvider[0]
    && p.indexOf('1,390원') >= 0 && p.indexOf('8월 14일 기준') >= 0
    && p.indexOf('국제 기준환율(ECB)') >= 0));
T('* Fact 주입 경로에 provider 분기가 없다 (구조로 보장)',
  /function factDirective\(fact\)/.test(htmlSrc)
  && !/factDirective\([^)]*provider/.test(htmlSrc)
  && !/function buildChatInstruction\(opts\)[\s\S]{0,4000}?opts\.provider/.test(htmlSrc));

/* ---------- 6. 대시보드 ---------- */
S('6. 유료 판단 대시보드');
const all = {
  '2026-08-18': { messages: 24, calls: 27, unservedMsgs: 1, degradedMsgs: 2, cacheHits: 4, dataCalls: 6,
                  e429: 4, e503: 2, kinds: { '429_RPD': 3, '429_RPM': 1 }, inferred: 1, rpdHit: 1,
                  errors: { 'gemini:flash': { '429_RPD': 2 }, 'groq:oss': { '429_RPD': 1 } },
                  rpdLimit: { 'gemini:flash': 200 } },
  '2026-08-17': { messages: 10, calls: 11, rpdHit: 1, errors: { 'gemini:flash': { '429_RPD': 1 } } },
  '2026-08-16': { messages: 8, calls: 8 }
};
const panel = renderQuotaPanel(all);
T('한도가 확정된 곳은 숫자를 보여준다', /한도 200회\/일/.test(panel), panel.slice(0, 200));
T('* 확정 못 한 곳은 "한도 미상" 으로 둔다', /한도 미상/.test(panel));
T('소진 일수를 센다 (2일)', /소진 2일/.test(panel), panel);
T('기준선을 화면에 함께 표시', /기준선 3일/.test(panel) && /14일 중 3일 소진/.test(panel));
T('기준선 미만이면 경고하지 않는다', !/기준선을 넘었습니다/.test(panel));
const over = Object.assign({}, all, { '2026-08-15': { messages: 5, calls: 5, rpdHit: 1, errors: {} } });
T('기준선 3일에 도달하면 전환 검토를 띄운다', /기준선을 넘었습니다/.test(renderQuotaPanel(over)));
const kinds = renderErrorKinds(all['2026-08-18']);
T('오류 분류를 많은 순으로 보여준다', kinds.indexOf('429_RPD') < kinds.indexOf('429_RPM'));
T('추정 건수를 따로 밝힌다', /추정 1/.test(kinds), kinds);
T('기준선이 CONFIG 에 있다', METRICS.baseline.rpdDays === 3 && METRICS.baseline.unservedRate === 0.03);
T('지난 날짜에 신규 필드가 없어도 죽지 않는다', typeof renderQuotaPanel({ '2026-08-01': { messages: 3, calls: 3 } }) === 'string');

/* ---------- 7. 기존 동작 회귀 ---------- */
S('7. 기존 동작 회귀');
T('FACT_RULES.llmAttempts = 1 (유지)', FACT_RULES.llmAttempts === 1);
T('FACT_RULES.waitOnQuota = false (유지)', FACT_RULES.waitOnQuota === false);
T('우아한 축소 설정 유지', DEGRADE_RULES.shrinkOnQuota === true && DEGRADE_RULES.lastResort === true);
T('Groq 7m30s 파싱 (v2.9.2 회귀)', sandbox.parseRetryAfterMs(noHeaders, 'try again in 7m30s') === 450000);
T('Gemini retryDelay 파싱 (v2.9.2 회귀)', sandbox.parseRetryAfterMs(noHeaders, '"retryDelay": "17s"') === 17000);
T('ms 를 s 보다 먼저 본다', sandbox.parseRetryAfterMs(noHeaders, 'try again in 500ms') === 500);
T('숫자 카드 문장이 살아 있다', /지금 자세한 설명은 어렵지만/.test(htmlSrc));

console.log('\n' + '-'.repeat(46) + '\n통과 ' + pass + ' · 실패 ' + fail);
process.exit(fail ? 1 : 0);
