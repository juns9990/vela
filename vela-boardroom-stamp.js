#!/usr/bin/env node
/*!
 * vela-boardroom-stamp.js — Compass 앱 셸 BUILD_ID 스탬프
 * ------------------------------------------------------------------
 *   실행:  node vela-boardroom-stamp.js
 *   시점:  vela-boardroom-prototype.html / manifest / 아이콘을 고친 뒤,
 *          git commit 하기 직전에 한 번. (의존성 없음 — Node 표준 모듈만)
 *
 * 무엇을 하나
 *   ① 앱 셸 파일들의 내용을 sha256 로 묶어 12자리 BUILD_ID 를 만든다.
 *   ② vela-boardroom-sw.js 의 __BUILD_ID__ 마커 사이에 그 값을 심는다.
 *      → 서비스워커 캐시 키가 "버전"이 아니라 "내용"을 따라간다.
 *   ③ HTML 의 manifest 링크 쿼리(?b=...)도 같은 값으로 맞춘다.
 *
 * 왜 필요한가 (Steel Calc v1.7.1 에서 검증된 문제)
 *   같은 버전으로 두 번 배포하면 sw.js 가 바이트 단위로 동일해서
 *   브라우저가 서비스워커 업데이트를 감지하지 못하고,
 *   캐시 키도 버전에만 묶여 있어 구버전 파일이 계속 나간다.
 *   BUILD_ID 를 쓰면 1바이트만 바뀌어도 캐시 키와 sw.js 가 함께 바뀌므로
 *   구버전 캐시가 남을 수 없다.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = __dirname;

/* 앱 셸 — 이 파일들의 내용이 BUILD_ID 를 결정한다.
 * (sw.js 자신은 넣지 않는다 — 넣으면 해시가 자기 자신을 참조해 순환한다) */
const SHELL_FOR_HASH = [
  'vela-boardroom-prototype.html',
  'vela-boardroom-manifest.json',
  'vela-boardroom-icon-192.png',
  'vela-boardroom-icon-512.png',
  'vela-boardroom-icon-192-maskable.png',
  'vela-boardroom-icon-512-maskable.png',
  'vela-boardroom-icon-180.png'
];

const SW_FILE = 'vela-boardroom-sw.js';
const HTML_FILE = 'vela-boardroom-prototype.html';

const MARK_BEGIN = '/* __BUILD_ID__ */';
const MARK_END = '/* __BUILD_ID_END__ */';

/* HTML 안의 manifest 링크 — 해시 계산에서 제외해야 순환하지 않는다.
 * (BUILD_ID 를 심으면 HTML 이 바뀌고, 그러면 해시가 또 바뀌므로
 *  해시를 낼 때는 이 쿼리 부분을 항상 고정 토큰으로 치환해서 계산한다) */
const MANIFEST_RE = /(vela-boardroom-manifest\.json\?b=)([A-Za-z0-9_]+)/;
const MANIFEST_NEUTRAL = 'vela-boardroom-manifest.json?b=__BUILD_ID__';

function readShellForHash(file) {
  const buf = fs.readFileSync(path.join(ROOT, file));
  if (file !== HTML_FILE) return buf;
  // HTML 은 manifest 쿼리를 중립화한 뒤 해시 (자기참조 방지)
  const neutral = buf.toString('utf8').replace(MANIFEST_RE, MANIFEST_NEUTRAL);
  return Buffer.from(neutral, 'utf8');
}

function shellBuildId() {
  const h = crypto.createHash('sha256');
  SHELL_FOR_HASH.forEach((f) => {
    const full = path.join(ROOT, f);
    if (!fs.existsSync(full)) {
      console.error('FAIL: 앱 셸 파일 없음 — ' + f);
      process.exit(1);
    }
    h.update(f).update('\0').update(readShellForHash(f));
  });
  return h.digest('hex').slice(0, 12);
}

function stampServiceWorker(id) {
  const p = path.join(ROOT, SW_FILE);
  const src = fs.readFileSync(p, 'utf8');
  const b = src.indexOf(MARK_BEGIN);
  const e = src.indexOf(MARK_END);
  if (b < 0 || e < 0 || e < b) {
    console.error('FAIL: ' + SW_FILE + ' 의 __BUILD_ID__ 마커를 찾을 수 없음');
    process.exit(1);
  }
  const next = src.slice(0, b + MARK_BEGIN.length) + " '" + id + "' " + src.slice(e);
  if (next !== src) {
    fs.writeFileSync(p, next);
    return true;
  }
  return false;
}

function stampHtml(id) {
  const p = path.join(ROOT, HTML_FILE);
  const src = fs.readFileSync(p, 'utf8');
  if (!MANIFEST_RE.test(src)) {
    console.error('FAIL: ' + HTML_FILE + ' 에서 manifest ?b= 쿼리를 찾을 수 없음');
    process.exit(1);
  }
  const next = src.replace(MANIFEST_RE, '$1' + id);
  if (next !== src) {
    fs.writeFileSync(p, next);
    return true;
  }
  return false;
}

function main() {
  const id = shellBuildId();
  const swChanged = stampServiceWorker(id);
  const htmlChanged = stampHtml(id);
  console.log('Vela Compass BUILD_ID = ' + id + '  (앱 셸 내용 해시)');
  console.log('  ' + SW_FILE + '  : ' + (swChanged ? '갱신됨' : '변경 없음'));
  console.log('  ' + HTML_FILE + ' : ' + (htmlChanged ? '갱신됨' : '변경 없음'));
  if (!swChanged && !htmlChanged) {
    console.log('  → 앱 셸이 이전 배포와 동일하다. 그대로 커밋해도 된다.');
  }
}

if (require.main === module) main();
module.exports = { shellBuildId: shellBuildId, SHELL_FOR_HASH: SHELL_FOR_HASH };
