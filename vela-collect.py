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

# 이미지 풀 (썸네일용 - 토픽별 매핑)
IMG_POOL = {
    "LLM":      "https://images.unsplash.com/photo-1639762681485-074b7f938ba0?w=400&q=70",
    "Vision":   "https://images.unsplash.com/photo-1518770660439-4636190af475?w=400&q=70",
    "Agent":    "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=400&q=70",
    "Robotics": "https://images.unsplash.com/photo-1531746790731-6c087fecd65a?w=400&q=70",
    "Safety":   "https://images.unsplash.com/photo-1620207418302-439b387441b0?w=400&q=70",
    "Audio":    "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=400&q=70",
    "Tool":     "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=400&q=70",
    "Infra":    "https://images.unsplash.com/photo-1591453089816-0fbb971b454c?w=400&q=70",
}
IMG_DEFAULT = IMG_POOL["LLM"]


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
    """간이 점수 (1-5). 발행 신선도 + 출처 권위 + 키워드 신호로 추정."""
    score = 3
    src = item.get("source", "")
    title = (item.get("title", "") + " " + item.get("abstract", "")).lower()
    if src == "blog" and any(d in item.get("url", "") for d in ["anthropic.com", "openai.com", "deepmind.google", "ai.googleblog", "blog.google"]):
        score = 5
    elif src == "github":
        score = 4
    elif src == "arxiv":
        score = 4 if any(k in title for k in ["sota", "state-of-the-art", "outperform", "frontier", "novel", "release"]) else 3
    if any(k in title for k in ["gpt-5", "claude 5", "gemini 2", "llama 4", "agi", "breakthrough"]):
        score = 5
    return min(5, max(1, score))


def make_id(prefix, raw):
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"{prefix}-{h}"


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
                "thumb": IMG_POOL.get(cat, IMG_DEFAULT)
            })
    except Exception as e:
        print(f"[arxiv {category}] error: {e}", file=sys.stderr)
    return items


def collect_rss(url, source_label, source_key):
    """RSS / Atom 피드 수집."""
    items = []
    try:
        xml = fetch(url, timeout=15)
        # RSS 2.0
        if "<rss" in xml or "<channel" in xml:
            root = ET.fromstring(xml)
            for it in root.findall(".//item")[:8]:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                desc = re.sub(r"<[^>]+>", " ", (it.findtext("description") or "")).strip()[:240]
                pub_raw = (it.findtext("pubDate") or "")
                try:
                    pub = datetime.strptime(pub_raw[:25], "%a, %d %b %Y %H:%M:%S").strftime("%Y-%m-%d")
                except Exception:
                    pub = datetime.now(KST).strftime("%Y-%m-%d")
                if not (title and link):
                    continue
                cat = categorize(title + " " + desc)
                items.append({
                    "id": make_id(source_key, link),
                    "source": "blog", "sourceLabel": source_label,
                    "title": title, "abstract": desc,
                    "url": link, "published": pub,
                    "tags": [cat], "authors": source_label,
                    "thumb": IMG_POOL.get(cat, IMG_DEFAULT)
                })
        # Atom
        else:
            ns = {"a": "http://www.w3.org/2005/Atom"}
            root = ET.fromstring(xml)
            for entry in root.findall("a:entry", ns)[:8]:
                title = (entry.findtext("a:title", "", ns) or "").strip()
                link = ""
                for l in entry.findall("a:link", ns):
                    if l.get("rel") == "alternate" or not l.get("rel"):
                        link = l.get("href"); break
                summary = (entry.findtext("a:summary", "", ns) or entry.findtext("a:content", "", ns) or "").strip()
                summary = re.sub(r"<[^>]+>", " ", summary)[:240]
                pub = (entry.findtext("a:updated", "", ns) or entry.findtext("a:published", "", ns) or "")[:10]
                if not (title and link):
                    continue
                cat = categorize(title + " " + summary)
                items.append({
                    "id": make_id(source_key, link),
                    "source": "blog", "sourceLabel": source_label,
                    "title": title, "abstract": summary,
                    "url": link, "published": pub or datetime.now(KST).strftime("%Y-%m-%d"),
                    "tags": [cat], "authors": source_label,
                    "thumb": IMG_POOL.get(cat, IMG_DEFAULT)
                })
    except Exception as e:
        print(f"[rss {source_label}] error: {e}", file=sys.stderr)
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
                "thumb": IMG_POOL.get(cat, IMG_DEFAULT)
            })
    except Exception as e:
        print(f"[github trending] error: {e}", file=sys.stderr)
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

    # 1. 수집
    pool = []
    print("\n[1/4] Collecting from sources...")
    pool += collect_arxiv("cs.AI", 12);  print(f"  ArXiv cs.AI: {len(pool)}")
    pool += collect_arxiv("cs.LG", 8);   print(f"  + cs.LG: {len(pool)}")
    pool += collect_arxiv("cs.CL", 8);   print(f"  + cs.CL: {len(pool)}")
    pool += collect_rss("https://www.anthropic.com/rss.xml", "Anthropic", "anth");   print(f"  + Anthropic: {len(pool)}")
    pool += collect_rss("https://openai.com/news/rss.xml", "OpenAI", "oai");          print(f"  + OpenAI: {len(pool)}")
    pool += collect_rss("https://research.google/blog/rss/", "Google Research", "g"); print(f"  + Google: {len(pool)}")
    pool += collect_rss("https://huggingface.co/blog/feed.xml", "HuggingFace", "hf"); print(f"  + HF: {len(pool)}")
    pool += collect_github_trending();   print(f"  + GitHub Trending: {len(pool)}")
    print(f"  Total raw: {len(pool)}")

    # 2. 점수 + 정렬
    print("\n[2/4] Scoring & dedup...")
    seen_urls = set()
    scored = []
    for item in pool:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        item["score"] = estimate_score(item)
        scored.append(item)
    scored.sort(key=lambda x: (-x["score"], x.get("published", "")), reverse=False)
    scored.sort(key=lambda x: -x["score"])
    print(f"  After dedup: {len(scored)}")

    # 3. 검증 — URL 살아있는지
    print("\n[3/4] Validating URLs (this takes a moment)...")
    validated = []
    for i, item in enumerate(scored[:30]):  # 상위 30개만 검증 (속도)
        if safe_get_url(item["url"]):
            validated.append(item)
        else:
            print(f"  ✗ Dead URL skipped: {item['url'][:60]}", file=sys.stderr)
        if len(validated) >= 16:
            break
    print(f"  Validated signals: {len(validated)}")

    # 영상 검증
    print("\n  Validating YouTube videos...")
    valid_videos = []
    for v in CURATED_VIDEOS:
        if validate_youtube(v["videoId"]):
            valid_videos.append({
                **v, "source": "YouTube",
                "thumb": f"https://i.ytimg.com/vi/{v['videoId']}/hqdefault.jpg"
            })
        else:
            print(f"  ✗ Dead video skipped: {v['videoId']} ({v['title']})", file=sys.stderr)
    print(f"  Validated videos: {len(valid_videos)}")

    if len(validated) < 5 or len(valid_videos) < 3:
        print("\n⚠️  Insufficient validated content. Aborting build to preserve last issue.", file=sys.stderr)
        sys.exit(1)

    # 4. 한국어 번역 (Groq 무료 API)
    print("\n[4/6] Translating to Korean (Groq AI)...")
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        validated = groq_translate(validated, groq_key)
    else:
        print("  ⚠️ GROQ_API_KEY env var not set — content remains in English")

    # 5. 빌드
    print("\n[5/6] Building issue JSON...")
    # Cover: 가장 점수 높고 영상 있는 항목 우선, 없으면 첫 영상
    cover_video = valid_videos[0]
    cover = {
        "label": f"Cover Story · Week {meta['issue_week']}",
        "headline": cover_video["title"].replace("—", "·"),
        "deck": f"이번 주 Vela가 추천하는 깊이 있는 강의. {cover_video['byline']}의 시그니처.",
        "byline": [f"By {cover_video['byline'].upper()}", cover_video["duration"], "Curated"],
        "image": "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?w=1600&q=80",
        "videoId": cover_video["videoId"],
        "credit": "Click image to play"
    }

    # This Month in AI: 이번 주 score 5 항목 4개
    top_items = [s for s in validated if s["score"] >= 4][:4]
    this_month = []
    for s in top_items:
        d = s.get("published", meta["monday"])
        try:
            date_label = datetime.strptime(d, "%Y-%m-%d").strftime("%b %d").upper()
        except Exception:
            date_label = "THIS WEEK"
        this_month.append({
            "date": date_label,
            "category": (s["tags"][0] if s.get("tags") else "Update"),
            "title": s["title"][:80],
            "deck": s["abstract"][:140],
            "image": s["thumb"],
            "url": s["url"]
        })

    # Featured: score 4+ 중에 cover 다음 3개
    featured_items = [s for s in validated if s["score"] >= 4][:3]
    featured = []
    for s in featured_items:
        featured.append({
            "label": s["tags"][0] if s.get("tags") else "Highlight",
            "title": s["title"][:80],
            "deck": s["abstract"][:140],
            "byline": f"{s['sourceLabel'].upper()} · {s['authors'][:30]}",
            "image": s["thumb"],
            "url": s["url"]
        })

    issue = {
        "version": "v0.15.0",
        "meta": meta,
        "cover": cover,
        "thisMonth": this_month,
        "featured": featured,
        "videos": valid_videos[:3],
        "signals": validated[:8]
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Issue built: {OUTPUT_PATH}")
    print(f"  Cover: {cover['headline'][:60]}")
    print(f"  This Month: {len(this_month)} items")
    print(f"  Featured: {len(featured)} items")
    print(f"  Videos: {len(valid_videos[:3])} items")
    print(f"  Signals: {len(validated[:8])} items")

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
GROQ_MODEL = "llama-3.3-70b-versatile"  # 한국어 지원 우수, 빠름

def groq_translate(items, api_key):
    """
    영문 abstract → 매거진 톤의 한국어 번역.
    items: dicts with 'title' and 'abstract' keys
    실패한 항목은 원문 그대로 반환 (전체 빌드는 계속).
    """
    if not api_key:
        print("  ⚠️ GROQ_API_KEY not set — skipping translation", file=sys.stderr)
        return items

    print(f"  Translating {len(items)} items via Groq ({GROQ_MODEL})...")
    success = 0
    for i, item in enumerate(items):
        # 한글이 이미 들어있으면 스킵 (시드 데이터 보존)
        if any('\uAC00' <= c <= '\uD7A3' for c in item.get("title", "")):
            continue

        prompt = f"""당신은 AI 매거진 'Vela'의 한국어 번역 에디터입니다.
아래 영문 논문/기사의 제목과 abstract를 매거진 톤(간결, 직관적, 호기심 자극)의 한국어로 번역해주세요.

규칙:
- 제목: 30자 이내, 매거진 헤드라인 톤 (의역 가능, 핵심 강조)
- abstract: 2~3문장, 140자 이내, 본문 첫 문장처럼 자연스럽게
- 기술 용어는 영어 원어 유지 가능 (예: Transformer, attention, MoE)
- 출력은 반드시 JSON 형식: {{"title": "...", "abstract": "..."}}

원본:
Title: {item.get('title', '')[:200]}
Abstract: {item.get('abstract', '')[:600]}

JSON만 출력:"""

        try:
            req = urllib.request.Request(
                GROQ_API_URL,
                data=json.dumps({
                    "model": GROQ_MODEL,
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
                    item["title"] = translated["title"][:120]
                if translated.get("abstract"):
                    item["abstract"] = translated["abstract"][:280]
                success += 1
        except urllib.error.HTTPError as e:
            err_body = ""
            try: err_body = e.read().decode("utf-8")[:200]
            except: pass
            print(f"  ✗ Translate failed [{i+1}/{len(items)}]: HTTP {e.code} {err_body}", file=sys.stderr)
        except Exception as e:
            print(f"  ✗ Translate failed [{i+1}/{len(items)}]: {e}", file=sys.stderr)

        # Rate limit 보호 (Groq 무료 30 RPM = 2초당 1회 안전)
        time.sleep(2.1)

    print(f"  ✓ Translated {success}/{len(items)} items")
    return items


if __name__ == "__main__":
    main()
