#!/usr/bin/env python3
"""
Vela Weekly Issue Collector · Phase 2
=====================================
매주 월요일 06:00 KST 자동 실행 (GitHub Actions cron).
외부 API 키 불필요 (모두 공개 RSS/API 사용).

수집 소스:
  - ArXiv API: cs.AI / cs.LG / cs.CL 카테고리 신규 논문
  - Anthropic 블로그 RSS
  - OpenAI 블로그 RSS
  - Google Research 블로그 RSS
  - HuggingFace blog RSS
  - GitHub Trending (Python AI repos)
  - 큐레이션 YouTube 영상 (Karpathy, 3Blue1Brown 등)

검증:
  - 모든 URL HTTP 200 확인
  - YouTube videoId 11자 + oEmbed로 활성 상태 확인
  - 검증 실패 시 해당 항목만 제외 (전체 빌드는 계속)

출력:
  - vela-issue.json (이번 주 매거진 데이터)
"""

import json
import os
import re
import sys
import time
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

# ============================================================
# 설정
# ============================================================
KST = timezone(timedelta(hours=9))
USER_AGENT = "Mozilla/5.0 (compatible; VelaBot/1.0; +https://juns9990.github.io/vela/)"
TIMEOUT = 15
OUTPUT_PATH = "vela-issue.json"
ARCHIVE_INDEX_PATH = "vela-archive.json"
RSS_PATH = "vela-rss.xml"

# 카테고리 키워드 매핑 (제목/abstract 매칭)
CATEGORY_RULES = [
    ("Vision",  ["diffusion", "image", "video gen", "vision-language", "vlm", "vit", "stable diffusion", "sora", "midjourney"]),
    ("Audio",   ["audio", "speech", "tts", "asr", "whisper", "voice"]),
    ("Robotics",["robot", "embodied", "manipulation", "vla "]),
    ("Agent",   ["agent", "tool use", "multi-agent", "autonomous"]),
    ("Safety",  ["alignment", "safety", "constitutional", "rlhf", "rlaif", "jailbreak"]),
    ("Infra",   ["inference", "vllm", "kv-cache", "serving", "training infra", "moe", "quantization"]),
    ("Tool",    ["framework", "library", "sdk", "toolkit", "ide"]),
    ("LLM",     ["llm", "language model", "transformer", "attention", "gpt", "llama", "mistral", "claude", "gemini", "deepseek"]),
]

# YouTube 큐레이션 (정적 — 강의/원리 영상은 자주 안 바뀌므로 손으로 관리)
CURATED_VIDEOS = [
    {"title": "Let's build GPT — 처음부터 만드는 GPT", "byline": "Andrej Karpathy", "duration": "1:56:20", "videoId": "kCc8FmEb1nY"},
    {"title": "[1시간] LLM 입문 강의", "byline": "Andrej Karpathy", "duration": "59:48", "videoId": "zjkBMFhNj_g"},
    {"title": "But what is a GPT? — 트랜스포머 시각 입문", "byline": "3Blue1Brown", "duration": "27:14", "videoId": "wjZofJX0v4M"},
    {"title": "신경망의 본질 — Deep Learning Chapter 1", "byline": "3Blue1Brown", "duration": "18:40", "videoId": "aircAruvnKk"},
    {"title": "Attention in transformers, visually explained", "byline": "3Blue1Brown", "duration": "26:10", "videoId": "eMlx5fFNoYc"},
    {"title": "How DeepSeek Rewrote the AI Playbook", "byline": "Computerphile", "duration": "16:33", "videoId": "gY4Z-9QlZ64"},
]

# 검증된 이미지 풀 (v0.18~v0.20에서 장기간 정상 작동 확인된 9개만 사용)
# 추측 ID 사용 금지 — 깨진 이미지 방지
VERIFIED_IMAGES = [
    "https://images.unsplash.com/photo-1639762681485-074b7f938ba0?w=600&q=70",  # 보라 큐브 (LLM)
    "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&q=70",  # 회로 (Vision)
    "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=600&q=70",  # 매트릭스 (Agent)
    "https://images.unsplash.com/photo-1531746790731-6c087fecd65a?w=600&q=70",  # 로봇팔 (Robotics)
    "https://images.unsplash.com/photo-1620207418302-439b387441b0?w=600&q=70",  # 추상 (Safety)
    "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=600&q=70",     # 네온 (Audio)
    "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=600&q=70",     # 코드 (Tool)
    "https://images.unsplash.com/photo-1591453089816-0fbb971b454c?w=600&q=70",  # 서버 (Infra)
    "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?w=600&q=70",  # 그라데이션
]

IMG_DEFAULT = VERIFIED_IMAGES[0]

# 호환성: 카테고리별 대표 이미지 (검증된 풀에서 매핑)
IMG_POOL = {
    "LLM":      VERIFIED_IMAGES[0],
    "Vision":   VERIFIED_IMAGES[1],
    "Agent":    VERIFIED_IMAGES[2],
    "Robotics": VERIFIED_IMAGES[3],
    "Safety":   VERIFIED_IMAGES[4],
    "Audio":    VERIFIED_IMAGES[5],
    "Tool":     VERIFIED_IMAGES[6],
    "Infra":    VERIFIED_IMAGES[7],
}

# 항목별 이미지 선택 — URL 해시로 검증된 풀에서 회전
# (카테고리 구분 없이 9개 공용 풀 사용 → 깨진 이미지 0, 항목마다 다양)
def pick_image(category, seed_str):
    """검증된 9개 풀에서 seed(URL)에 따라 회전 선택. 절대 깨지지 않음."""
    if not seed_str:
        return VERIFIED_IMAGES[0]
    idx = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest(), 16) % len(VERIFIED_IMAGES)
    return VERIFIED_IMAGES[idx]

# 커버(메인) 이미지 — 검증된 풀에서 주차별 회전 (1600px 크게)
def pick_cover_image(week_seed):
    """발행 주차에 따라 검증된 풀에서 커버 선택 (1600px)."""
    idx = int(hashlib.md5(str(week_seed).encode("utf-8")).hexdigest(), 16) % len(VERIFIED_IMAGES)
    # w=600 → w=1600으로 교체해 큰 커버용
    return VERIFIED_IMAGES[idx].replace("w=600&q=70", "w=1600&q=80")


# ============================================================
# HTTP / 유틸
# ============================================================
def fetch(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def categorize(text):
    t = (text or "").lower()
    for cat, kws in CATEGORY_RULES:
        if any(k in t for k in kws):
            return cat
    return "LLM"


def estimate_score(item):
    """점수 (1-5). 화제성·인기주제·권위·신선도 종합. 손이 가는 항목이 위로."""
    score = 2.5  # 기본값 낮춤 (무명 항목은 아래로)
    src = item.get("source", "")
    url = item.get("url", "")
    title_raw = item.get("title", "")
    title = (title_raw + " " + item.get("abstract", "")).lower()

    # 1) 출처 권위 (대형 연구소 블로그 = 높음)
    AUTHORITY = ["anthropic.com", "openai.com", "deepmind.google", "ai.googleblog",
                 "blog.google", "ai.meta.com", "mistral.ai", "huggingface.co"]
    if src == "blog" and any(d in url for d in AUTHORITY):
        score += 1.5
    elif src == "github":
        score += 1.0
    elif src == "news":
        score += 0.5

    # 2) 화제성 키워드 (사람들이 클릭하는 단어) — 강한 가중치
    HOT_TOPICS = [
        "gpt-5", "gpt5", "claude", "gemini", "llama 4", "llama4", "deepseek",
        "agent", "agentic", "multi-agent", "autonomous",  # 에이전트 AI ← 요청
        "generative", "diffusion", "text-to-", "image gen", "video gen",  # 생성형 AI ← 요청
        "reasoning", "o1", "o3", "chain-of-thought",  # 추론
        "open-source", "open source", "open weights", "release", "launch",
        "multimodal", "vision-language", "rag", "fine-tun",
        "benchmark", "sota", "state-of-the-art", "outperform", "frontier",
        "breakthrough", "agi", "scaling",
    ]
    hot_hits = sum(1 for k in HOT_TOPICS if k in title)
    score += min(1.5, hot_hits * 0.5)  # 화제 키워드 많을수록 (최대 +1.5)

    # 3) HN 점수 반영 (커뮤니티 화제성)
    authors = item.get("authors", "")
    if "pts" in authors:
        try:
            pts = int(authors.split()[0])
            if pts >= 200: score += 1.5
            elif pts >= 100: score += 1.0
            elif pts >= 50: score += 0.5
        except Exception:
            pass

    # 4) 제목 품질 (너무 짧거나 학술 약어 범벅이면 감점)
    if len(title_raw) < 20:
        score -= 0.5

    return min(5, max(1, round(score)))


def make_id(prefix, raw):
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"{prefix}-{h}"


def fetch_og_image(url, timeout=8):
    """기사/블로그 페이지에서 og:image 메타태그 추출. 실패 시 None."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read(100000).decode("utf-8", errors="ignore")
    except Exception:
        return None
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            img = m.group(1).strip()
            if img.startswith("//"):
                img = "https:" + img
            elif img.startswith("/"):
                from urllib.parse import urlparse
                p = urlparse(url)
                img = f"{p.scheme}://{p.netloc}{img}"
            if img.startswith("http") and len(img) < 500:
                return img
    return None


def fetch_unsplash_keyword(keywords, api_key, seed_str=""):
    """Unsplash API로 키워드 관련 사진 검색. API 키 없으면 None."""
    if not api_key or not keywords:
        return None
    query = "+".join(keywords[:2])
    try:
        url = f"https://api.unsplash.com/search/photos?query={query}&per_page=10&orientation=landscape&content_filter=high"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Client-ID {api_key}",
            "User-Agent": USER_AGENT
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
            results = data.get("results", [])
            if results:
                idx = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest(), 16) % len(results) if seed_str else 0
                raw = results[idx].get("urls", {}).get("raw", "")
                if raw:
                    return raw + "&w=600&q=70&fit=crop"
    except Exception:
        pass
    return None


CATEGORY_KEYWORDS = {
    "LLM":      ["artificial intelligence", "neural network"],
    "Vision":   ["computer vision", "camera technology"],
    "Agent":    ["automation", "robot assistant"],
    "Robotics": ["robotics", "robot arm"],
    "Safety":   ["cybersecurity", "data protection"],
    "Audio":    ["sound wave", "audio technology"],
    "Tool":     ["coding", "software development"],
    "Infra":    ["data center", "server technology"],
}


def resolve_image(item, unsplash_key=None):
    """하이브리드 이미지: og:image → Unsplash 키워드 → 검증된 풀."""
    src = item.get("source", "")
    url = item.get("url", "")
    cat = (item.get("tags") or ["LLM"])[0]
    if src in ("blog", "news"):
        og = fetch_og_image(url)
        if og:
            return og
    if unsplash_key:
        kws = CATEGORY_KEYWORDS.get(cat, ["artificial intelligence"])
        title = item.get("title", "").lower()
        if "agent" in title: kws = ["ai agent", "automation"]
        elif "diffusion" in title or "image" in title: kws = ["digital art", "generative"]
        elif "robot" in title: kws = ["robotics", "robot"]
        u = fetch_unsplash_keyword(kws, unsplash_key, seed_str=url)
        if u:
            return u
    return pick_image(cat, url)


def diversify_by_topic(items, max_per_topic=3):
    """주제 다양성 보장 — 상위권에서 한 카테고리가 독식하지 않게 재정렬.
    점수 순서는 최대한 유지하되, 같은 카테고리가 연속/과다하지 않도록 분산."""
    if not items:
        return items
    # 카테고리별 큐 분리 (점수 순 유지)
    from collections import defaultdict, deque
    buckets = defaultdict(deque)
    for it in items:
        cat = (it.get("tags") or ["LLM"])[0]
        buckets[cat].append(it)

    # 라운드로빈으로 뽑되, 점수 높은 카테고리부터
    result = []
    topic_count = defaultdict(int)
    remaining = sum(len(q) for q in buckets.values())

    while remaining > 0:
        # 이번 라운드: 각 카테고리에서 가장 점수 높은 것 후보로
        candidates = []
        for cat, q in buckets.items():
            if q:
                candidates.append((cat, q[0]))
        if not candidates:
            break
        # 후보 중 점수 높은 순, 단 이미 많이 뽑힌 주제는 후순위
        candidates.sort(key=lambda c: (
            -c[1].get("score", 0) + topic_count[c[0]] * 1.2  # 많이 뽑힌 주제 페널티
        ))
        cat, item = candidates[0]
        buckets[cat].popleft()
        result.append(item)
        topic_count[cat] += 1
        remaining -= 1

    return result


def safe_get_url(url, max_redirects=3):
    """URL 검증 - HTTP 200 확인 (HEAD 우선, 실패 시 GET)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 400
    except (urllib.error.HTTPError, urllib.error.URLError, Exception):
        # HEAD 실패 시 GET로 재시도 (일부 서버는 HEAD 거부)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as r:
                return 200 <= r.status < 400
        except Exception:
            return False


def validate_youtube(video_id):
    """YouTube oEmbed로 영상 활성 상태 확인."""
    if not re.fullmatch(r"[\w-]{11}", video_id or ""):
        return False
    try:
        fetch(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json", timeout=8)
        return True
    except Exception:
        return False


# ============================================================
# 수집기
# ============================================================
def collect_arxiv(category="cs.AI", max_results=15):
    """ArXiv API: 최근 논문 수집."""
    items = []
    try:
        url = f"http://export.arxiv.org/api/query?search_query=cat:{category}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
        xml = fetch(url, timeout=20)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml)
        for entry in root.findall("a:entry", ns):
            title = (entry.findtext("a:title", "", ns) or "").strip().replace("\n", " ")
            summary = (entry.findtext("a:summary", "", ns) or "").strip().replace("\n", " ")[:280]
            link = ""
            for l in entry.findall("a:link", ns):
                if l.get("type") == "text/html" or l.get("rel") == "alternate":
                    link = l.get("href"); break
            if not link:
                link = (entry.findtext("a:id", "", ns) or "").strip()
            pub = (entry.findtext("a:published", "", ns) or "")[:10]
            authors = [a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)]
            author_str = (authors[0] + " et al.") if len(authors) > 1 else (authors[0] if authors else "")
            cat = categorize(title + " " + summary)
            arxiv_id = re.search(r"abs/([\d.]+)", link)
            arxiv_id = arxiv_id.group(1) if arxiv_id else link[-12:]
            items.append({
                "id": f"arxiv-{arxiv_id}",
                "source": "arxiv",
                "sourceLabel": "ArXiv",
                "title": title,
                "abstract": summary,
                "url": link,
                "published": pub or datetime.now(KST).strftime("%Y-%m-%d"),
                "tags": [cat] + (["Architecture"] if "transformer" in (title+summary).lower() else []),
                "authors": author_str or "ArXiv",
                "thumb": pick_image(cat, link)
            })
    except Exception as e:
        print(f"[arxiv {category}] error: {e}", file=sys.stderr)
    return items


def collect_rss(url, source_label, source_key):
    """RSS / Atom 피드 수집. 다양한 변종 대응."""
    items = []
    try:
        xml = fetch(url, timeout=15)
        # 네임스페이스 prefix 제거 (atom:, dc:, content: 등)
        xml = re.sub(r'<(/?)\w+:', r'<\1', xml)
        # RSS 2.0
        if "<rss" in xml[:500] or "<channel" in xml[:1500]:
            try:
                root = ET.fromstring(xml)
            except ET.ParseError:
                # XML 파싱 실패 시 정규식 폴백
                return _rss_regex_fallback(xml, source_label, source_key)
            for it in root.findall(".//item")[:8]:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                desc_raw = (it.findtext("description") or it.findtext("encoded") or "")
                desc = re.sub(r"<[^>]+>", " ", desc_raw)
                desc = re.sub(r"&\w+;", " ", desc)  # &nbsp; 등
                desc = re.sub(r"\s+", " ", desc).strip()[:240]
                pub_raw = (it.findtext("pubDate") or "")
                try:
                    pub = datetime.strptime(pub_raw[:25], "%a, %d %b %Y %H:%M:%S").strftime("%Y-%m-%d")
                except Exception:
                    pub = datetime.now(KST).strftime("%Y-%m-%d")
                if not (title and link) or len(desc) < 20:
                    continue
                cat = categorize(title + " " + desc)
                items.append({
                    "id": make_id(source_key, link),
                    "source": "blog", "sourceLabel": source_label,
                    "title": title[:200], "abstract": desc,
                    "url": link, "published": pub,
                    "tags": [cat], "authors": source_label,
                    "thumb": pick_image(cat, link)
                })
        # Atom
        else:
            try:
                root = ET.fromstring(xml)
            except ET.ParseError:
                return _rss_regex_fallback(xml, source_label, source_key)
            # 네임스페이스 제거 후라 직접 entry 찾기
            for entry in root.findall(".//entry")[:8]:
                title = (entry.findtext("title") or "").strip()
                link = ""
                for l in entry.findall("link"):
                    if l.get("rel") == "alternate" or not l.get("rel"):
                        link = l.get("href", ""); break
                if not link:
                    link = (entry.findtext("id") or "").strip()
                summary = (entry.findtext("summary") or entry.findtext("content") or "").strip()
                summary = re.sub(r"<[^>]+>", " ", summary)
                summary = re.sub(r"&\w+;", " ", summary)
                summary = re.sub(r"\s+", " ", summary).strip()[:240]
                pub = (entry.findtext("updated") or entry.findtext("published") or "")[:10]
                if not (title and link) or len(summary) < 20:
                    continue
                cat = categorize(title + " " + summary)
                items.append({
                    "id": make_id(source_key, link),
                    "source": "blog", "sourceLabel": source_label,
                    "title": title[:200], "abstract": summary,
                    "url": link, "published": pub or datetime.now(KST).strftime("%Y-%m-%d"),
                    "tags": [cat], "authors": source_label,
                    "thumb": pick_image(cat, link)
                })
    except Exception as e:
        print(f"[rss {source_label}] error: {e}", file=sys.stderr)
    return items


def _rss_regex_fallback(xml, source_label, source_key):
    """XML 파싱 실패 시 정규식으로 최소한 추출 시도."""
    items = []
    try:
        # <item>...</item> 또는 <entry>...</entry>
        blocks = re.findall(r"<(?:item|entry)[^>]*>(.*?)</(?:item|entry)>", xml, re.DOTALL)
        for block in blocks[:6]:
            title_m = re.search(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.DOTALL)
            link_m = re.search(r"<link[^>]*>(?:<!\[CDATA\[)?(https?://[^<\]]+)", block)
            desc_m = re.search(r"<description[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", block, re.DOTALL)
            if not title_m or not link_m:
                continue
            title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()[:200]
            link = link_m.group(1).strip()
            desc = re.sub(r"<[^>]+>", " ", desc_m.group(1) if desc_m else "")
            desc = re.sub(r"\s+", " ", desc).strip()[:240]
            if len(desc) < 20:
                continue
            cat = categorize(title + " " + desc)
            items.append({
                "id": make_id(source_key, link),
                "source": "blog", "sourceLabel": source_label,
                "title": title, "abstract": desc,
                "url": link, "published": datetime.now(KST).strftime("%Y-%m-%d"),
                "tags": [cat], "authors": source_label,
                "thumb": pick_image(cat, link)
            })
    except Exception as e:
        print(f"[rss fallback {source_label}] error: {e}", file=sys.stderr)
    return items


def collect_github_trending():
    """GitHub Trending — HTML 스크래핑 (공식 API에 trending이 없음)."""
    items = []
    try:
        html = fetch("https://github.com/trending/python?since=weekly", timeout=15)
        # article 블록 추출
        articles = re.findall(r'<article class="Box-row">(.*?)</article>', html, re.DOTALL)
        for art in articles[:10]:
            m = re.search(r'<h2[^>]*>\s*<a href="(/[^"]+)"', art)
            if not m: continue
            repo_path = m.group(1).strip()
            repo_name = repo_path.lstrip("/").replace("/", " / ")
            # 설명
            desc_m = re.search(r'<p class="col-9 color-fg-muted my-1 pr-4">(.*?)</p>', art, re.DOTALL)
            desc = re.sub(r"<[^>]+>", " ", desc_m.group(1)).strip() if desc_m else ""
            desc = re.sub(r"\s+", " ", desc)[:220]
            # 별 개수
            stars_m = re.search(r'<svg[^>]+octicon-star[^>]+>.*?</svg>\s*([\d,]+)', art, re.DOTALL)
            stars = stars_m.group(1).strip() if stars_m else ""
            # AI/ML 관련성 필터
            if not any(k in (repo_name + " " + desc).lower() for k in
                       ["ai", "ml", "llm", "agent", "model", "neural", "deep", "gpt", "transformer", "diffusion", "rag", "vector"]):
                continue
            cat = categorize(repo_name + " " + desc)
            items.append({
                "id": make_id("gh", repo_path),
                "source": "github", "sourceLabel": "GitHub",
                "title": repo_name + (" — " + desc.split(".")[0] if desc else ""),
                "abstract": desc or "Trending Python repository this week.",
                "url": "https://github.com" + repo_path,
                "published": datetime.now(KST).strftime("%Y-%m-%d"),
                "tags": [cat, "Tool"],
                "authors": f"{stars} ★" if stars else "GitHub Trending",
                "thumb": pick_image(cat, "https://github.com" + repo_path)
            })
    except Exception as e:
        print(f"[github trending] error: {e}", file=sys.stderr)
    return items


def collect_hackernews_ai():
    """Hacker News에서 AI 키워드 포함된 인기 글 수집."""
    items = []
    try:
        # HN Algolia API: front_page 글 중 AI 관련
        url = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"
        data = json.loads(fetch(url, timeout=15))
        ai_keywords = ["ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic",
                       "machine learning", "neural", "diffusion", "transformer",
                       "deepseek", "model", "agent", "rag", "embedding"]
        for hit in data.get("hits", []):
            title = (hit.get("title") or "").strip()
            url_link = (hit.get("url") or hit.get("story_url") or "").strip()
            if not (title and url_link):
                continue
            if not any(k in title.lower() for k in ai_keywords):
                continue
            # 최소 score (HN points)
            points = hit.get("points", 0) or 0
            if points < 30:  # 30점 미만은 노이즈
                continue
            cat = categorize(title)
            items.append({
                "id": make_id("hn", url_link),
                "source": "news",
                "sourceLabel": "Hacker News",
                "title": title,
                "abstract": f"Hacker News 인기글. {points}점 · {hit.get('num_comments', 0) or 0}개 댓글.",
                "url": url_link,
                "published": (hit.get("created_at") or "")[:10] or datetime.now(KST).strftime("%Y-%m-%d"),
                "tags": [cat, "Industry"],
                "authors": f"{points} pts",
                "thumb": pick_image(cat, url_link)
            })
            if len(items) >= 8:
                break
    except Exception as e:
        print(f"[hackernews] error: {e}", file=sys.stderr)
    return items


def collect_hf_daily_papers():
    """HuggingFace Daily Papers — 매일 큐레이션되는 핫한 논문."""
    items = []
    try:
        html = fetch("https://huggingface.co/papers", timeout=15)
        # 페이퍼 카드 추출 (a href="/papers/2401.xxxxx")
        paper_links = list(set(re.findall(r'href="(/papers/\d{4}\.\d{4,5})"', html)))[:8]
        for link in paper_links:
            paper_url = "https://huggingface.co" + link
            arxiv_id = link.split("/")[-1]
            arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
            try:
                # 페이퍼 페이지에서 제목 추출
                paper_html = fetch(paper_url, timeout=10)
                title_m = re.search(r'<title>([^<|]+)', paper_html)
                title = title_m.group(1).strip() if title_m else f"Paper {arxiv_id}"
                title = re.sub(r"\s+", " ", title)[:200]
                # 간단한 description (HF는 abstract를 JS로 그려서 정규식 추출 어려움)
                desc = "HuggingFace Daily Papers에 큐레이션된 주목받는 논문."
            except Exception:
                title = f"HuggingFace Daily Paper · {arxiv_id}"
                desc = "이번 주 주목받은 논문 중 하나."
            cat = categorize(title)
            items.append({
                "id": f"arxiv-{arxiv_id}",
                "source": "arxiv",
                "sourceLabel": "HF Daily",
                "title": title,
                "abstract": desc,
                "url": arxiv_url,
                "published": datetime.now(KST).strftime("%Y-%m-%d"),
                "tags": [cat],
                "authors": "Daily Papers",
                "thumb": pick_image(cat, arxiv_url)
            })
    except Exception as e:
        print(f"[hf-daily] error: {e}", file=sys.stderr)
    return items


# ============================================================
# 메인
# ============================================================
def get_issue_meta():
    now = datetime.now(KST)
    if now.hour < 6:
        now -= timedelta(days=1)
    monday = now - timedelta(days=now.weekday())
    iso_year, iso_week, _ = monday.isocalendar()
    return {
        "issue_year": iso_year,
        "issue_week": iso_week,
        "monday": monday.strftime("%Y-%m-%d"),
        "next_monday": (monday + timedelta(days=7)).strftime("%Y-%m-%d"),
        "generated_at": datetime.now(KST).isoformat()
    }


def main():
    print("=" * 60)
    print("Vela Weekly Collector · Starting")
    print("=" * 60)

    meta = get_issue_meta()
    print(f"Issue: {meta['issue_year']}-W{meta['issue_week']} (Monday {meta['monday']})")

    # ============================================================
    # 1. 수집 — 25+ 소스 (학술 / 기업 / 산업뉴스 / 커뮤니티)
    # ============================================================
    pool = []
    print("\n[1/6] Collecting from 25+ sources...")

    # --- 학술 (ArXiv) ---
    print("  ▸ Academic")
    pool += collect_arxiv("cs.AI", 15)
    pool += collect_arxiv("cs.LG", 10)
    pool += collect_arxiv("cs.CL", 10)
    pool += collect_arxiv("cs.CV", 8)   # Vision 추가
    pool += collect_arxiv("cs.RO", 5)   # Robotics 추가
    print(f"    ArXiv (5 cats): {len(pool)} items")

    # --- AI 기업·연구소 블로그 (15개) ---
    print("  ▸ Company/Lab Blogs")
    BLOG_SOURCES = [
        ("https://www.anthropic.com/rss.xml",       "Anthropic",       "anth"),
        ("https://openai.com/news/rss.xml",          "OpenAI",          "oai"),
        ("https://research.google/blog/rss/",        "Google Research", "goog"),
        ("https://blog.google/technology/ai/rss/",   "Google AI",       "googai"),
        ("https://huggingface.co/blog/feed.xml",     "HuggingFace",     "hf"),
        ("https://ai.meta.com/blog/rss/",            "Meta AI",         "meta"),
        ("https://machinelearning.apple.com/rss.xml","Apple ML",        "apple"),
        ("https://blogs.nvidia.com/feed/",           "NVIDIA",          "nvid"),
        ("https://www.microsoft.com/en-us/research/feed/",  "Microsoft Research", "msr"),
        ("https://mistral.ai/news/rss.xml",          "Mistral AI",      "mistral"),
        ("https://deepmind.google/blog/rss.xml",     "DeepMind",        "dm"),
        ("https://stability.ai/news?format=rss",     "Stability AI",    "stab"),
        ("https://www.together.ai/blog?format=rss",  "Together AI",     "tog"),
        ("https://cohere.com/blog/rss.xml",          "Cohere",          "coh"),
        ("https://lmsys.org/rss.xml",                "LMSYS",           "lmsys"),
        # 에이전트 AI 전문 소스 (요청)
        ("https://blog.langchain.dev/rss/",          "LangChain",       "lc"),
        ("https://www.llamaindex.ai/blog/feed.xml",  "LlamaIndex",      "li"),
        # 생성형 AI / 이미지·영상 전문 소스 (요청)
        ("https://runwayml.com/blog/rss.xml",        "Runway",          "rway"),
        ("https://blog.fal.ai/rss/",                 "fal",             "fal"),
    ]
    blog_count = 0
    for url, label, key in BLOG_SOURCES:
        before = len(pool)
        pool += collect_rss(url, label, key)
        added = len(pool) - before
        if added > 0:
            blog_count += added
    print(f"    Blogs: {blog_count} items")

    # --- 산업·뉴스 미디어 ---
    print("  ▸ Tech News")
    NEWS_SOURCES = [
        ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch",   "tc"),
        ("https://www.theverge.com/ai-artificial-intelligence/rss/index.xml", "The Verge", "verge"),
        ("https://venturebeat.com/category/ai/feed/", "VentureBeat",       "vb"),
        ("https://feeds.arstechnica.com/arstechnica/technology-lab",  "Ars Technica", "ars"),
        ("https://www.wired.com/feed/tag/ai/latest/rss",  "Wired AI",      "wired"),
    ]
    news_count = 0
    for url, label, key in NEWS_SOURCES:
        before = len(pool)
        items = collect_rss(url, label, key)
        # 뉴스 미디어는 AI 관련만 필터 (제목+description에 AI 키워드)
        items = [
            it for it in items
            if any(k in (it.get("title", "") + " " + it.get("abstract", "")).lower()
                   for k in ["ai", "artificial intelligence", "llm", "machine learning",
                             "neural", "gpt", "claude", "gemini", "openai", "anthropic",
                             "deepseek", "model", "agent"])
        ]
        for it in items:
            it["sourceLabel"] = label
            it["source"] = "news"
            it["tags"] = it.get("tags", []) + ["Industry"]
        pool += items
        news_count += len(items)
    print(f"    News (AI-filtered): {news_count} items")

    # --- 커뮤니티 / 큐레이션 ---
    print("  ▸ Community")
    pool += collect_hackernews_ai();         print(f"    HN AI: total {len(pool)}")
    pool += collect_hf_daily_papers();       print(f"    HF Daily Papers: total {len(pool)}")
    pool += collect_github_trending();       print(f"    GH Trending: total {len(pool)}")

    print(f"\n  Total raw: {len(pool)}")

    # ============================================================
    # 2. 정리 — URL dedup + 제목 유사도 dedup + 점수
    # ============================================================
    print("\n[2/6] Scoring & dedup (URL + title similarity)...")
    seen_urls = set()
    seen_title_tokens = []  # (set of normalized tokens)
    scored = []

    def title_tokens(title):
        """제목에서 불용어 제거 후 토큰 셋 반환 (유사도 비교용)."""
        title = re.sub(r"[^a-zA-Z0-9가-힣\s]", " ", title.lower())
        stop = {"the", "a", "an", "of", "for", "in", "on", "to", "with", "and", "or",
                "is", "are", "was", "were", "be", "by", "as", "at", "from", "this",
                "that", "we", "our", "new", "ai", "model", "models"}
        return {w for w in title.split() if len(w) > 2 and w not in stop}

    def jaccard(a, b):
        if not a or not b: return 0.0
        return len(a & b) / len(a | b)

    for item in pool:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        abstract = (item.get("abstract") or "").strip()

        # 빈 항목 / 너무 짧은 abstract 완화 (20자 → 15자)
        if not url or not title:
            continue
        if len(abstract) < 15:
            continue

        # URL 중복
        url_norm = url.split("?")[0].rstrip("/")
        if url_norm in seen_urls:
            continue

        # 제목 유사도 0.75 이상이면 중복 처리 (이전 0.6 → 0.75 완화)
        # 0.6은 너무 엄격해서 비슷한 주제 논문이 잘림
        toks = title_tokens(title)
        is_dup = False
        for prev in seen_title_tokens:
            if jaccard(toks, prev) >= 0.75:
                is_dup = True; break
        if is_dup:
            continue

        seen_urls.add(url_norm)
        if len(toks) >= 2:
            seen_title_tokens.append(toks)

        item["score"] = estimate_score(item)
        scored.append(item)

    scored.sort(key=lambda x: (-x.get("score", 0), x.get("published", "")), reverse=False)
    scored.sort(key=lambda x: -x.get("score", 0))
    print(f"  After dedup: {len(scored)} unique items")

    # ============================================================
    # 3. 학술 vs 산업 분리
    # ============================================================
    academic = [s for s in scored if s.get("source") in ("arxiv", "blog", "github", "huggingface")]
    industry = [s for s in scored if s.get("source") == "news"]
    print(f"  Academic pool: {len(academic)}, Industry pool: {len(industry)}")

    # 주제 다양성 재정렬 — 생성형/에이전트/멀티모달 등이 골고루 노출되게
    # (점수 순서 유지하되 한 주제 독식 방지)
    academic = diversify_by_topic(academic)
    # 카테고리 분포 출력 (진단용)
    from collections import Counter
    cat_dist = Counter((s.get("tags") or ["?"])[0] for s in academic[:20])
    print(f"  Topic distribution (top 20): {dict(cat_dist)}")

    # 4. 검증 — URL 살아있는지 (학술 30개 + 산업 15개까지 시도, 검증 실패해도 보존)
    print("\n[3/6] Validating URLs...")
    validated_academic = []
    failed_count = 0
    for item in academic[:60]:  # 더 많이 시도
        if safe_get_url(item["url"]):
            validated_academic.append(item)
        else:
            failed_count += 1
            # ArXiv 항목은 검증 실패해도 보존 (가끔 ArXiv 일시 차단됨)
            if item.get("source") == "arxiv":
                validated_academic.append(item)
        if len(validated_academic) >= 30:
            break
    print(f"  Academic validated: {len(validated_academic)} (skipped {failed_count} dead URLs)")

    validated_industry = []
    for item in industry[:30]:
        if safe_get_url(item["url"]):
            validated_industry.append(item)
        if len(validated_industry) >= 15:
            break
    print(f"  Industry validated: {len(validated_industry)}")

    # 영상 검증
    print("  Validating YouTube videos...")
    valid_videos = []
    for v in CURATED_VIDEOS:
        if validate_youtube(v["videoId"]):
            valid_videos.append({
                **v, "source": "YouTube",
                "thumb": f"https://i.ytimg.com/vi/{v['videoId']}/hqdefault.jpg"
            })
        else:
            print(f"  ✗ Dead video skipped: {v['videoId']} ({v['title']})", file=sys.stderr)
    print(f"  Videos validated: {len(valid_videos)}")

    # 최소 콘텐츠 체크 (전체 기준 완화: academic OR industry 한쪽이라도 충분하면 OK)
    if len(validated_academic) < 5 or len(valid_videos) < 3:
        print("\n⚠️  Insufficient validated content. Aborting build.", file=sys.stderr)
        sys.exit(1)

    # ============================================================
    # 5. 한국어 번역 (Groq) — 표시될 항목만, 산업 우선
    # ============================================================
    print("\n[4/6] Translating to Korean (Groq AI)...")
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    working_model = None
    if groq_key:
        # 매거진에 실제 표시되는 만큼만 번역 (학술 20 + 산업 8 = 28개)
        # 산업 먼저 번역 → 한도 도달 전에 Industry 섹션 보장
        academic_to_translate = validated_academic[:20]
        industry_to_translate = validated_industry[:8]
        # 산업 먼저 (UI에서 위쪽에 보이는 영역도 보장)
        merged = industry_to_translate + academic_to_translate
        print(f"  Translating {len(industry_to_translate)} industry + {len(academic_to_translate)} academic = {len(merged)} total")
        merged, working_model = groq_translate(merged, groq_key)
        # 분리 복구 (순서 바뀐 것 다시 원래대로)
        ind_n = len(industry_to_translate)
        translated_industry = merged[:ind_n]
        translated_academic = merged[ind_n:]
        # 원본 리스트에 번역 결과 머지 (번역 안 된 나머지는 그대로 유지)
        validated_industry = translated_industry + validated_industry[8:]
        validated_academic = translated_academic + validated_academic[20:]
    else:
        print("  ⚠️ GROQ_API_KEY env var not set — content remains in English")

    # ============================================================
    # 5.3. 하이브리드 이미지 — 표시될 항목만 (og:image + Unsplash 키워드 + 폴백)
    # ============================================================
    print("\n[이미지] Resolving hybrid images (og:image + fallback)...")
    unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip() or None
    if unsplash_key:
        print("  ✓ Unsplash API key found — 키워드 검색 활성화")
    else:
        print("  · Unsplash 키 없음 — og:image + 검증된 풀만 사용 (정상 작동)")
    img_resolved = 0
    # 표시되는 항목만 (This Month 6 + Featured 5 + Signals 20 + Industry 8 ≈ 상위 20 academic + 8 industry)
    for item in validated_academic[:20] + validated_industry[:8]:
        new_img = resolve_image(item, unsplash_key)
        if new_img and new_img != item.get("thumb"):
            item["thumb"] = new_img
            img_resolved += 1
    print(f"  ✓ {img_resolved}개 항목 이미지 갱신 (og:image 또는 키워드 검색)")

    # ============================================================
    # 5.5. Magazine Edition — Editor's Note + Trend Spotting
    # ============================================================
    editors_note = None
    trend_clusters = None
    if working_model:
        print("\n[Magazine] Generating Editor's Note...")
        editors_note = generate_editors_note(validated_academic, groq_key, working_model)
        if editors_note:
            print(f"  ✓ Editor's Note: {editors_note[:80]}...")
        time.sleep(2.5)  # rate limit

        print("[Magazine] Clustering trends...")
        trend_clusters = cluster_by_topic(validated_academic[:8], groq_key, working_model, max_clusters=3)
        if trend_clusters:
            print(f"  ✓ Trends: {[c['theme'] for c in trend_clusters]}")
        time.sleep(2.5)

    # Numbers This Week (LLM 호출 없음, 자동 계산)
    numbers = compute_numbers(
        validated_academic, validated_industry,
        blogs_count=blog_count, news_count=news_count,
        total_raw=len(pool)
    )

    # 6. 빌드
    print("\n[5/6] Building issue JSON...")
    # Cover: 영상 우선
    cover_video = valid_videos[0]
    cover = {
        "label": f"Cover Story · Week {meta['issue_week']}",
        "headline": cover_video["title"].replace("—", "·"),
        "deck": f"이번 주 Vela가 추천하는 깊이 있는 강의. {cover_video['byline']}의 시그니처.",
        "byline": [f"By {cover_video['byline'].upper()}", cover_video["duration"], "Curated"],
        "image": pick_cover_image(f"{meta['issue_year']}-{meta['issue_week']}"),
        "videoId": cover_video["videoId"],
        "credit": "Click image to play"
    }

    # This Month: score 3+ 6개 (4+에서 완화 — 카드가 1~2개만 나오는 문제 해결)
    top_items = [s for s in validated_academic if s.get("score", 0) >= 3][:6]
    # 그래도 부족하면 점수 무관하게 상위 6개 채우기
    if len(top_items) < 6:
        seen_urls = {x.get("url") for x in top_items}
        for s in validated_academic:
            if s.get("url") not in seen_urls:
                top_items.append(s)
            if len(top_items) >= 6:
                break
    this_month = []
    for s in top_items:
        d = s.get("published", meta["monday"])
        try:
            date_label = datetime.strptime(d, "%Y-%m-%d").strftime("%b %d").upper()
        except Exception:
            date_label = "THIS WEEK"
        this_month.append({
            "date": date_label,
            "category": (s.get("tags") or ["Update"])[0],
            "title": s.get("title", "")[:80],
            "deck": s.get("abstract", "")[:140],
            "why": s.get("why", "")[:120],
            "image": s.get("thumb", IMG_DEFAULT),
            "url": s.get("url", "")
        })

    # Featured: 학술 5개 (This Month와 다른 항목 우선)
    used_urls = {x.get("url") for x in this_month}
    featured_items = [s for s in validated_academic if s.get("url") not in used_urls][:5]
    # 부족하면 중복 허용해서라도 5개 채움
    if len(featured_items) < 5:
        for s in validated_academic:
            if s not in featured_items:
                featured_items.append(s)
            if len(featured_items) >= 5:
                break
    featured = []
    for s in featured_items:
        featured.append({
            "label": (s.get("tags") or ["Highlight"])[0],
            "title": s.get("title", "")[:80],
            "deck": s.get("abstract", "")[:140],
            "why": s.get("why", "")[:120],
            "byline": f"{s.get('sourceLabel', 'Vela').upper()} · {s.get('authors', '')[:30]}",
            "image": s.get("thumb", IMG_DEFAULT),
            "url": s.get("url", "")
        })

    # Industry: 산업 뉴스 8개
    industry_items = validated_industry[:8]
    industry_section = []
    for s in industry_items:
        d = s.get("published", meta["monday"])
        try:
            date_label = datetime.strptime(d, "%Y-%m-%d").strftime("%b %d").upper()
        except Exception:
            date_label = "THIS WEEK"
        industry_section.append({
            "date": date_label,
            "source": s.get("sourceLabel", "Industry"),
            "title": s.get("title", "")[:100],
            "deck": s.get("abstract", "")[:160],
            "url": s.get("url", "")
        })

    issue = {
        "version": "v0.20.0",
        "meta": meta,
        "editorsNote": editors_note,
        "trends": trend_clusters,
        "numbers": numbers,
        "cover": cover,
        "thisMonth": this_month,
        "featured": featured,
        "videos": valid_videos[:4],
        "industry": industry_section,
        "signals": validated_academic[:20]
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Issue built: {OUTPUT_PATH}")
    print(f"  Cover: {cover['headline'][:60]}")
    print(f"  This Month: {len(this_month)} items")
    print(f"  Featured: {len(featured)} items")
    print(f"  Videos: {len(valid_videos[:4])} items")
    print(f"  Industry: {len(industry_section)} items")
    print(f"  Signals: {len(validated_academic[:20])} items")

    # 6. 과거 이슈 아카이브 — 이번 주 스냅샷 별도 파일로 저장
    print("\n[6/6] Archiving snapshot + generating RSS...")
    archive_filename = f"vela-issue-{meta['issue_year']}-W{meta['issue_week']:02d}.json"
    with open(archive_filename, "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Snapshot: {archive_filename}")
    update_archive_index(issue, archive_filename)

    # 7. RSS 피드 생성
    write_rss(issue)
    print(f"  ✓ RSS: {RSS_PATH}")

    print("=" * 60)


def update_archive_index(issue, snapshot_filename):
    """vela-archive.json 인덱스 파일 갱신 — 모든 과거 이슈의 메타데이터 누적."""
    import os
    meta = issue["meta"]
    cover = issue["cover"]
    headline_plain = re.sub(r"<[^>]+>", "", cover.get("headline", "")).strip()

    new_entry = {
        "file": snapshot_filename,
        "year": meta["issue_year"],
        "week": meta["issue_week"],
        "monday": meta["monday"],
        "headline": headline_plain[:120],
        "signal_count": len(issue.get("signals", []))
    }

    # 기존 인덱스 읽기
    archive = {"version": "1.0", "issues": []}
    if os.path.exists(ARCHIVE_INDEX_PATH):
        try:
            with open(ARCHIVE_INDEX_PATH, encoding="utf-8") as f:
                archive = json.load(f)
        except Exception as e:
            print(f"  ⚠️ archive read failed, starting fresh: {e}", file=sys.stderr)
            archive = {"version": "1.0", "issues": []}

    # 같은 주 항목 있으면 교체, 없으면 추가
    issues = [i for i in archive.get("issues", []) if not (i.get("year") == new_entry["year"] and i.get("week") == new_entry["week"])]
    issues.append(new_entry)
    # 최신순 정렬 (year/week DESC)
    issues.sort(key=lambda x: (x.get("year", 0), x.get("week", 0)), reverse=True)
    archive["issues"] = issues
    archive["updated_at"] = datetime.now(KST).isoformat()

    with open(ARCHIVE_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Archive index: {len(issues)} issues total")


def xml_escape(s):
    """RSS XML escape."""
    return (str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("'", "&apos;"))


def write_rss(issue):
    """vela-rss.xml 생성 — 이번 주 핵심 항목들로 RSS 2.0 피드."""
    meta = issue["meta"]
    site_url = "https://juns9990.github.io/vela/vela-prototype.html"
    pub_date = datetime.now(KST).strftime("%a, %d %b %Y %H:%M:%S +0900")

    items_xml = []

    # Cover (영상이라 site URL로)
    cover = issue.get("cover", {})
    if cover:
        headline = re.sub(r"<[^>]+>", "", cover.get("headline", ""))
        items_xml.append(f"""    <item>
      <title>[Cover] {xml_escape(headline)}</title>
      <link>{xml_escape(site_url)}</link>
      <guid isPermaLink="false">vela-cover-{meta['issue_year']}-W{meta['issue_week']:02d}</guid>
      <description>{xml_escape(cover.get('deck', ''))}</description>
      <pubDate>{pub_date}</pubDate>
      <category>Cover Story</category>
    </item>""")

    # Signals (각 항목)
    for s in issue.get("signals", []):
        cat = (s.get("tags") or ["AI"])[0]
        items_xml.append(f"""    <item>
      <title>[{xml_escape(cat)}] {xml_escape(s.get('title', ''))}</title>
      <link>{xml_escape(s.get('url', ''))}</link>
      <guid isPermaLink="true">{xml_escape(s.get('url', ''))}</guid>
      <description>{xml_escape(s.get('abstract', ''))}</description>
      <pubDate>{pub_date}</pubDate>
      <category>{xml_escape(cat)}</category>
      <source url="{xml_escape(site_url)}">{xml_escape(s.get('sourceLabel', 'Vela'))}</source>
    </item>""")

    # Featured
    for f in issue.get("featured", []):
        if not f.get("url"):
            continue
        items_xml.append(f"""    <item>
      <title>[Featured] {xml_escape(f.get('title', ''))}</title>
      <link>{xml_escape(f.get('url', ''))}</link>
      <guid isPermaLink="true">{xml_escape(f.get('url', ''))}</guid>
      <description>{xml_escape(f.get('deck', ''))}</description>
      <pubDate>{pub_date}</pubDate>
      <category>Featured</category>
    </item>""")

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Vela — AI Intelligence Magazine</title>
    <link>{xml_escape(site_url)}</link>
    <atom:link href="https://juns9990.github.io/vela/vela-rss.xml" rel="self" type="application/rss+xml" />
    <description>매주 월요일 자동 발행되는 AI 매거진. 파편을 매거진으로, 신호를 항해로.</description>
    <language>ko</language>
    <pubDate>{pub_date}</pubDate>
    <lastBuildDate>{pub_date}</lastBuildDate>
    <generator>Vela Weekly Collector</generator>
    <ttl>10080</ttl>
{chr(10).join(items_xml)}
  </channel>
</rss>
"""
    with open(RSS_PATH, "w", encoding="utf-8") as f:
        f.write(rss_xml)


# ============================================================
# Groq AI 한국어 번역 (무료 API)
# ============================================================
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# 번역 모델 폴백 체인 — 일일 한도(RPD) 큰 순서로 우선
# Llama 3.1 8B: 14,400 RPD (14배 여유) ← 1순위
# Llama 3.3 70B: 1,000 RPD ← 2순위 (8B 실패 시)
# GPT-OSS 120B: 1,000 RPD ← 3순위
GROQ_MODELS = [
    "llama-3.1-8b-instant",       # 1순위: 일일 14,400회, 빠름, 한국어 충분
    "llama-3.3-70b-versatile",    # 2순위: 품질 더 좋지만 일일 1,000회만
    "openai/gpt-oss-120b",        # 3순위: 최후 폴백
]
GROQ_MODEL = GROQ_MODELS[0]  # 기본값 (호환성)

# 자주 등장하는 한자 → 한글 변환 (LLM이 가끔 한자로 떨어뜨릴 때 안전망)
HANJA_MAP = {
    "最新": "최신", "人工知能": "인공지능", "技術": "기술", "性能": "성능",
    "開發": "개발", "硏究": "연구", "改善": "개선", "向上": "향상",
    "提供": "제공", "適用": "적용", "活用": "활용", "效率": "효율",
    "效果": "효과", "結果": "결과", "可能": "가능", "重要": "중요",
    "問題": "문제", "解決": "해결", "方法": "방법", "新": "신",
    "舊": "구", "大": "대", "小": "소", "高": "고", "低": "저",
    "速度": "속도", "規模": "규모", "本": "본", "次": "차",
    "先": "선", "後": "후", "前": "전", "全": "전", "新規": "신규",
    "公開": "공개", "發表": "발표", "登場": "등장", "出市": "출시",
    "限界": "한계", "增加": "증가", "減少": "감소", "競爭": "경쟁",
    "協力": "협력", "開": "개", "發": "발", "化": "화", "性": "성",
}

def strip_hanja(text):
    """한자를 한글로 변환하거나 제거. LLM이 가끔 한자를 떨어뜨릴 때 안전망."""
    if not text:
        return text
    # 1) 사전에 있는 한자 단어 변환
    for hanja, hangul in HANJA_MAP.items():
        text = text.replace(hanja, hangul)
    # 2) 남아있는 단일 한자 제거 (한자 유니코드 범위)
    text = re.sub(r'[\u4E00-\u9FFF\u3400-\u4DBF]', '', text)
    # 3) 한자 제거로 인한 공백 정리
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def groq_translate(items, api_key):
    """
    영문 abstract → 매거진 톤의 한국어 번역.
    items: dicts with 'title' and 'abstract' keys
    실패한 항목은 원문 그대로 반환 (전체 빌드는 계속).
    """
    if not api_key:
        print("  ⚠️ GROQ_API_KEY not set — skipping translation", file=sys.stderr)
        return items, None

    # ─── 모델 자동 선택: 폴백 체인에서 첫 번째 작동하는 모델 찾기 ───
    working_model = None
    print(f"  Testing Groq models...")
    for model in GROQ_MODELS:
        try:
            test_req = urllib.request.Request(
                GROQ_API_URL,
                data=json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with: OK"}],
                    "max_tokens": 10
                }).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT
                },
                method="POST"
            )
            with urllib.request.urlopen(test_req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
                if data.get("choices"):
                    working_model = model
                    print(f"  ✓ Using model: {model}")
                    break
        except urllib.error.HTTPError as e:
            err_body = ""
            try: err_body = e.read().decode("utf-8")[:200]
            except: pass
            print(f"  ✗ Model {model}: HTTP {e.code} — {err_body[:120]}", file=sys.stderr)
        except Exception as e:
            print(f"  ✗ Model {model}: {type(e).__name__} — {str(e)[:120]}", file=sys.stderr)

    if not working_model:
        print(f"  ⚠️ ALL MODELS FAILED — Groq API 접근 불가. 콘텐츠가 영문으로 남습니다.", file=sys.stderr)
        print(f"  점검 사항: (1) GROQ_API_KEY Secret 등록 (2) https://console.groq.com 에서 키 활성 (3) 한도 초과 여부", file=sys.stderr)
        return items, None

    print(f"  Translating {len(items)} items via Groq ({working_model})...")
    success = 0
    fail_count = 0
    fail_reasons = {}
    skipped_korean = 0

    for i, item in enumerate(items):
        # 한글이 이미 들어있으면 스킵 (시드 데이터 보존)
        if any('\uAC00' <= c <= '\uD7A3' for c in item.get("title", "")):
            skipped_korean += 1
            continue

        prompt = f"""당신은 AI 매거진 'Vela'의 한국어 번역 에디터입니다.
아래 영문 논문/기사를 매거진 톤(간결, 직관적, 호기심 자극)의 한국어로 번역해주세요.

번역 규칙:
- **한자 절대 금지**: 모든 단어를 한글로만 작성. '最新' → '최신', '人工知能' → '인공지능'. 한자는 한 글자도 출력하지 마세요.
- 외래어/기술 용어는 영어 원어 유지 가능 (예: Transformer, attention, MoE, LLM)
- 제목: 30자 이내, 매거진 헤드라인 톤 (의역 가능, 핵심 강조)
- abstract: 2~3문장, 140자 이내, 본문 첫 문장처럼 자연스럽게
- why: 30~50자 한 줄. "왜 이게 중요한가"를 매거진 에디터 시각으로. AI 산업 맥락에서의 의미.

why 예시:
- "ChatGPT 메모리 기능과 정면 경쟁할 신기술"
- "오픈소스 진영의 GPT-5 대응책으로 주목"
- "에이전트 평가 기준이 정적에서 동적으로 이동"

출력은 반드시 JSON: {{"title": "...", "abstract": "...", "why": "..."}}

원본:
Title: {item.get('title', '')[:200]}
Abstract: {item.get('abstract', '')[:600]}

JSON만 출력:"""

        try:
            req = urllib.request.Request(
                GROQ_API_URL,
                data=json.dumps({
                    "model": working_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 400,
                    "response_format": {"type": "json_object"}
                }).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"].strip()
                # JSON 파싱
                translated = json.loads(content)
                if translated.get("title"):
                    item["title"] = strip_hanja(translated["title"][:120])
                if translated.get("abstract"):
                    item["abstract"] = strip_hanja(translated["abstract"][:280])
                if translated.get("why"):
                    item["why"] = strip_hanja(translated["why"][:120])
                success += 1
        except urllib.error.HTTPError as e:
            fail_count += 1
            err_body = ""
            try: err_body = e.read().decode("utf-8")[:300]
            except: pass
            reason = f"HTTP {e.code}"
            fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
            if fail_count <= 3:
                print(f"  ✗ Translate failed [{i+1}/{len(items)}]: HTTP {e.code} — {err_body[:200]}", file=sys.stderr)
            # 429 (rate limit) 만나면 60초 대기 후 자동 재개
            if e.code == 429:
                print(f"  ⏸ Rate limit hit — waiting 60s before continuing...", file=sys.stderr)
                time.sleep(60)
        except json.JSONDecodeError as e:
            fail_count += 1
            fail_reasons["JSON parse"] = fail_reasons.get("JSON parse", 0) + 1
            if fail_count <= 3:
                print(f"  ✗ Translate failed [{i+1}/{len(items)}]: JSON parse error", file=sys.stderr)
        except Exception as e:
            fail_count += 1
            reason = type(e).__name__
            fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
            if fail_count <= 3:
                print(f"  ✗ Translate failed [{i+1}/{len(items)}]: {reason} — {str(e)[:150]}", file=sys.stderr)

        # Rate limit 보호 (Llama 3.1 8B는 RPD 14,400, RPM 30 — 2.2초 페이스로 안전)
        time.sleep(2.2)

    total = len(items)
    print(f"  ✓ Translated {success}/{total} items (skipped {skipped_korean} already-Korean, failed {fail_count})")
    if fail_reasons:
        print(f"    Failure breakdown: {dict(fail_reasons)}", file=sys.stderr)
    if success == 0 and total > skipped_korean:
        print(f"  ⚠️ ALL TRANSLATIONS FAILED — 콘텐츠가 영문으로 남습니다. GROQ_API_KEY 또는 모델 상태를 확인하세요.", file=sys.stderr)

    return items, working_model
    return items


def generate_editors_note(items, api_key, working_model):
    """이번 주 콘텐츠를 보고 Editor's Note 생성. 70B 모델 우선 사용 (품질 보장)."""
    if not api_key or not items:
        return None

    # Editor's Note는 매주 1회뿐이라 70B 모델 직접 사용 (품질 우선)
    # 70B 실패 시 working_model로 폴백
    editor_model = "llama-3.3-70b-versatile"

    # 상위 8개 제목만 (간결하게)
    top = items[:8]
    bullets = "\n".join([
        f"- {it.get('title', '')[:50]}"
        for it in top
    ])
    prompt = f"""당신은 AI 매거진 'Vela'의 편집장입니다.
아래 항목들을 보고 매거진 첫 머리에 들어갈 매우 짧은 'Editor's Note'를 한국어로 작성하세요.

엄격한 제약 (반드시 지키세요):
1. 정확히 1~2문장만. 총 80자 이내. 절대 그 이상 쓰지 마세요.
2. 이번 주 AI 흐름의 핵심 한 가지만 짚으세요. 여러 흐름 나열 금지.
3. 한자 절대 금지. 외래어/기술용어는 영어 그대로 (예: Gemma, Transformer)
4. 반드시 마침표(.)로 끝내세요. 절대 중간에 끊지 마세요.
5. 따옴표 없이 본문만.

좋은 예시:
"이번 주 AI 모델들은 한 방향으로 모이고 있다. 더 자연스럽고, 더 빠르게."
"에이전트 평가 기준이 정적에서 동적으로 이동하는 흐름이 뚜렷하다."

이번 주 항목:
{bullets}

Editor's Note (1~2문장, 80자 이내, 마침표로 종료):"""

    # 70B 먼저 시도 → 실패 시 working_model 폴백
    for model_to_try in [editor_model, working_model]:
        if not model_to_try:
            continue
        try:
            req = urllib.request.Request(
                GROQ_API_URL,
                data=json.dumps({
                    "model": model_to_try,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,  # 0.7 → 0.5 더 일관되게
                    "max_tokens": 600  # 한국어 80자 = 약 200~300토큰, 여유 둠
                }).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read().decode("utf-8"))
                note = data["choices"][0]["message"]["content"].strip()

                # 후처리 1: 한자 제거
                note = strip_hanja(note)

                # 후처리 2: 마크다운/따옴표/별표 제거
                note = re.sub(r'^["\'\*\s\-]+|["\'\*\s]+$', '', note)
                note = re.sub(r'\s+', ' ', note).strip()

                # 후처리 3: 100자 넘으면 마지막 완전한 문장까지만
                if len(note) > 100:
                    # 첫 두 문장만 가져오기
                    sentences = re.split(r'(?<=[.!?])\s+', note)
                    if len(sentences) >= 2:
                        note = ' '.join(sentences[:2]).strip()
                    else:
                        # 마지막 마침표 위치
                        last_period = max(
                            note.rfind('.', 0, 100),
                            note.rfind('!', 0, 100),
                            note.rfind('?', 0, 100)
                        )
                        if last_period > 30:
                            note = note[:last_period + 1].strip()

                # 후처리 4: 마침표로 끝나지 않으면 강제
                if note and not note.endswith(('.', '?', '!')):
                    # "다", "요" 같은 한국어 종결어미로 끝나면 마침표 추가
                    if note.endswith(('다', '요', '음', '함', '됨', '었다', '있다')):
                        note += '.'
                    else:
                        # 마지막 완전한 문장 찾기
                        last = max(note.rfind('.'), note.rfind('!'), note.rfind('?'))
                        if last > 20:
                            note = note[:last + 1]
                        # 그래도 마침표 없으면 그냥 마침표 추가
                        elif note:
                            note = note.rstrip() + '.'

                # 후처리 5: 너무 짧거나 비어있으면 None
                if not note or len(note) < 20:
                    print(f"  ✗ Editor's Note too short, skipping", file=sys.stderr)
                    return None

                print(f"  ✓ Editor's Note ({model_to_try}): {note[:60]}...")
                return note[:200]  # 200자 하드 캡

        except urllib.error.HTTPError as e:
            print(f"  ✗ Editor's Note ({model_to_try}) failed: HTTP {e.code}", file=sys.stderr)
            continue  # 다음 모델로
        except Exception as e:
            print(f"  ✗ Editor's Note ({model_to_try}) failed: {e}", file=sys.stderr)
            continue

    return None


def cluster_by_topic(items, api_key, working_model, max_clusters=3):
    """이번 달 항목을 주제별 묶음으로 변환 (Trend Spotting)."""
    if not api_key or not working_model or len(items) < 4:
        return None
    bullets = "\n".join([
        f"{i+1}. {it.get('title', '')[:80]}"
        for i, it in enumerate(items[:8])
    ])
    prompt = f"""당신은 AI 매거진 'Vela'의 편집자입니다.
아래 8개 항목을 주제별로 2~3개의 클러스터로 묶어주세요.

요구사항:
- 각 클러스터는 명확한 한국어 주제명 (15자 이내)
- 각 항목은 1번부터 8번까지의 번호로 참조
- 주제명은 매거진 헤드라인 톤 (예: '에이전트의 진화', '추론 효율 경쟁')
- 한자 금지

출력 형식 (정확히 이 JSON 구조):
{{"clusters": [
  {{"theme": "주제명1", "items": [1, 3, 5]}},
  {{"theme": "주제명2", "items": [2, 4]}},
  {{"theme": "주제명3", "items": [6, 7, 8]}}
]}}

항목:
{bullets}

JSON만 출력:"""

    try:
        req = urllib.request.Request(
            GROQ_API_URL,
            data=json.dumps({
                "model": working_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 400,
                "response_format": {"type": "json_object"}
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].strip()
            parsed = json.loads(content)
            clusters = parsed.get("clusters", [])[:max_clusters]
            # 인덱스 검증 + 한자 제거
            valid = []
            for c in clusters:
                theme = strip_hanja(c.get("theme", ""))[:30]
                idxs = [i for i in c.get("items", []) if isinstance(i, int) and 1 <= i <= len(items)]
                if theme and idxs:
                    valid.append({"theme": theme, "indices": idxs})
            return valid if valid else None
    except Exception as e:
        print(f"  ✗ Trend clustering failed: {e}", file=sys.stderr)
        return None


def compute_numbers(academic, industry, blogs_count, news_count, total_raw):
    """Numbers This Week — 자동 계산되는 통계 박스 데이터."""
    # 이번 주 발표된 항목 (지난 7일 이내)
    today = datetime.now(KST).date()
    week_ago = today - timedelta(days=7)
    fresh_count = 0
    for item in (academic + industry):
        try:
            pub = datetime.strptime(item.get("published", ""), "%Y-%m-%d").date()
            if pub >= week_ago:
                fresh_count += 1
        except Exception:
            pass

    # 최고 점수 항목
    top_item = max(academic, key=lambda x: x.get("score", 0)) if academic else None
    top_label = (top_item.get("title", "")[:30] + "…") if top_item else "—"

    # 카테고리 빈도
    cat_count = {}
    for item in academic:
        cat = (item.get("tags") or ["기타"])[0]
        cat_count[cat] = cat_count.get(cat, 0) + 1
    top_category = max(cat_count.items(), key=lambda x: x[1])[0] if cat_count else "—"

    return {
        "raw_collected": total_raw,
        "academic_count": len(academic),
        "industry_count": len(industry),
        "fresh_this_week": fresh_count,
        "top_category": top_category,
        "top_score_title": top_label,
        "blog_sources": blogs_count,
        "news_sources": news_count,
    }


if __name__ == "__main__":
    main()
