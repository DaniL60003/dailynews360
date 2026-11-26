import datetime as dt
import json
import pathlib
import urllib.request
import urllib.parse
import re
import html
import concurrent.futures
import difflib
import feedparser

from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).parent
ARCHIVE = ROOT / "archive"
ARCHIVE.mkdir(exist_ok=True)

NOW = dt.datetime.now(ZoneInfo("Europe/Sofia"))
TODAY = NOW.date().isoformat()

MAX_NEWS = 5
MAX_AGE = dt.timedelta(hours=24)
HEADERS = {"User-Agent": "Mozilla/5.0"}

FEEDS = {
    "Meduza": "https://meduza.io/rss/all",
    "BBC Russian": "https://feeds.bbci.co.uk/russian/rss.xml",
    "Deutsche Welle": "https://rss.dw.com/rdf/rss-ru-all",
    "RFI": "https://www.rfi.fr/ru/rss",
    "Настоящее время": "https://www.currenttime.tv/api/zmgqoe$moi",
    "Euronews": "https://ru.euronews.com/rss",
    "Вести Израиль": "https://www.vesty.co.il/Integration/StoryRss2.xml",
    "NEWSru.co.il": "https://www.newsru.co.il/rss/index.xml",
    "Детали": "https://detaly.co.il/feed/",
    "Курсор": "https://cursorinfo.co.il/feed/",
    "MIGnews": "https://mignews.com/rss/",
    "BG-24": "https://bg-24.com/feed/",
    "BurgasMedia": "https://burgasmedia.com/rss",
    "The Bell": "https://thebell.io/rss",
    "Forbes Kazakhstan": "https://forbes.kz/rss/",
    "Хабр": "https://habr.com/ru/rss/news/?fl=ru",
    "N+1": "https://nplus1.net/rss.xml",
    "Хайтек": "https://hightech.fm/feed",
    "ITC": "https://itc.ua/feed/"
}

KEYWORDS = [
    r".",
    r"европ|нато|герман|франци|брюссел|евросоюз|ес\b|польш|британ",
    r"израил|цахал|газ[аеы]|иран|ливан|хамас|сири|иерусалим|тель.авив",
    r"болгар|бургас|несеб|влас|софи[яи]|варн|пловдив|помори",
    r"эконом|финанс|банк|рынок|нефт|бизнес|инвест|бирж|валют|инфляц",
    r"технолог|спутник|телеком|scpc|vsat|starlink|eutelsat|intelsat|интернет|искусственн|ии\b|космос"
]

SATELLITE = re.compile(
    r"scpc|vsat|спутник|телеком|starlink|eutelsat|intelsat",
    re.I
)

def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def allowed(url):
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (
            parsed.scheme == "https"
            and bool(host)
            and not host.endswith(".ru")
            and host != "ru"
        )
    except Exception:
        return False

def russian(text):
    letters = re.findall(r"[^\W\d_]", text, re.UNICODE)
    cyrillic = re.findall(r"[А-Яа-яЁё]", text)
    if not letters or len(cyrillic) < 5:
        return False

    if len(cyrillic) / len(letters) < 0.55:
        return False

    if re.search(r"[іїєґў]", text, re.I):
        return False

    return True

def verify_link(url):
    if not allowed(url):
        return None

    for method in ("HEAD", "GET"):
        try:
            request = urllib.request.Request(
                url, headers=HEADERS, method=method
            )
            with urllib.request.urlopen(
                request, timeout=10
            ) as response:
                final = response.geturl()
                if allowed(final):
                    return final
                return None
        except Exception:
            continue

    return None

def fetch_feed(pair):
    source, url = pair
    results = []

    try:
        if not allowed(url):
            return results

        request = urllib.request.Request(
            url, headers=HEADERS
        )

        with urllib.request.urlopen(
            request, timeout=20
        ) as response:
            if not allowed(response.geturl()):
                return results

            feed = feedparser.parse(response.read())

        for entry in feed.entries[:60]:
            title = clean(entry.get("title"))
            summary = clean(entry.get("summary"))[:450]

            if not russian(title):
                continue

            stamp = entry.get("published_parsed")
            if not stamp:
                stamp = entry.get("updated_parsed")

            if not stamp:
                continue

            published = dt.datetime(
                *stamp[:6], tzinfo=dt.timezone.utc
            )

            age = NOW - published

            if not dt.timedelta(0) <= age <= MAX_AGE:
                continue

            link = verify_link(entry.get("link", ""))

            if not link:
                continue

            results.append({
                "title": title,
                "summary": summary,
                "url": link,
                "source": source,
                "date": published.isoformat()
            })

        print(f"OK: {source}: {len(results)} news")

    except Exception as error:
        print(f"RSS ERROR: {source}: {error}")

    return results

def normalize(title):
    return re.sub(
        r"[\W_]+", " ", title.lower()
    ).strip()

def duplicate(item, selected):
    for old in selected:
        if item["url"] == old["url"]:
            return True

        ratio = difflib.SequenceMatcher(
            None,
            normalize(item["title"]),
            normalize(old["title"])
        ).ratio()

        if ratio >= 0.82:
            return True

    return False

with concurrent.futures.ThreadPoolExecutor(
    max_workers=12
) as pool:
    items = [
        item
        for group in pool.map(fetch_feed, FEEDS.items())
        for item in group
    ]

items.sort(
    key=lambda item: item["date"],
    reverse=True
)

if not items:
    raise SystemExit(
        "No fresh verified news. Previous edition preserved."
    )

sections = [[] for _ in range(6)]
selected = []

for category in [3, 2, 5, 4, 1, 0]:
    candidates = list(items)

    if category == 5:
        candidates.sort(
            key=lambda item: (
                bool(SATELLITE.search(
                    item["title"] + " " + item["summary"]
                )),
                item["date"]
            ),
            reverse=True
        )

    for item in candidates:
        if len(sections[category]) >= MAX_NEWS:
            break

        content = item["title"] + " " + item["summary"]

        if not re.search(
            KEYWORDS[category], content, re.I
        ):
            continue

        if duplicate(item, selected):
            continue

        sections[category].append(item)
        selected.append(item)

total = sum(map(len, sections))

if total == 0:
    raise SystemExit("Empty edition. Previous edition preserved.")

target = ARCHIVE / f"{TODAY}.json"

if target.exists():
    previous = json.loads(
        target.read_text(encoding="utf-8")
    )

    old_total = sum(
        map(len, previous.get("sections", []))
    )

    if old_total > total:
        raise SystemExit(
            "Incomplete update. Existing edition preserved."
        )

edition = {
    "date": TODAY,
    "updated": NOW.isoformat(),
    "sections": sections
}

target.write_text(
    json.dumps(edition, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

cutoff = (
    NOW.date() - dt.timedelta(days=29)
).isoformat()

for path in ARCHIVE.glob("*.json"):
    if path.stem < cutoff:
        path.unlink()

editions = sorted(
    [path.stem for path in ARCHIVE.glob("*.json")],
    reverse=True
)

(ROOT / "editions.json").write_text(
    json.dumps(editions, ensure_ascii=False),
    encoding="utf-8"
)

print(f"SUCCESS: {total} news")
for number, section in enumerate(sections, 1):
    print(f"Section {number}: {len(section)} news")
