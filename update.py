import datetime as dt, json, pathlib, urllib.request, urllib.parse, re, html, concurrent.futures
import feedparser
from zoneinfo import ZoneInfo
now=dt.datetime.now(ZoneInfo('Europe/Sofia')); root=pathlib.Path(__file__).parent; archive=root/'archive'; archive.mkdir(exist_ok=True)
queries=['мировые новости','Европа ЕС НАТО','Израиль Ближний Восток','Болгария Бургас Святой Влас','мировая экономика бизнес финансы','технологии спутниковая связь телекоммуникации']
feeds=['https://meduza.io/rss/all','https://feeds.bbci.co.uk/russian/rss.xml','https://www.dw.com/ru/rss/s-32780','https://www.newsru.co.il/rss/all.xml','https://www.vesty.co.il/Integration/StoryRss2.xml','https://habr.com/ru/rss/news/?fl=ru']
# Google News RSS provides topical discovery; only direct publisher URLs are accepted, so opaque Google links are skipped.
keywords=[r'.',r'европ|нато|герман|франци|ес\b',r'израил|газ[аеы]|иран|ливан|хамас|сири',r'болгар|бургас|несеб|влас|софи[яи]',r'эконом|финанс|банк|рынок|нефт|бизнес|инвест',r'технолог|спутник|телеком|scpc|интернет|искусственн|ии\b']
feeds += ['https://www.rfi.fr/ru/rss','https://www.currenttime.tv/api/zmgqoe$moi','https://thebell.io/rss','https://nplus1.net/rss','https://bnr.bg/ru/rss','https://www.bta.bg/ru/rss']
def clean(s): return html.unescape(re.sub('<[^>]+>',' ',s or '')).strip()
def fetch(url):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'DailyNews360/1.0'}),timeout=15) as r: f=feedparser.parse(r.read())
  out=[]
  for e in f.entries[:50]:
   t=e.get('published_parsed') or e.get('updated_parsed'); link=e.get('link',''); title=clean(e.get('title')); desc=clean(e.get('summary'))[:450]
   if not t or not re.search('[А-Яа-яЁё]',title): continue
   stamp=dt.datetime(*t[:6],tzinfo=dt.timezone.utc)
   if not dt.timedelta(0)<=now-stamp<=dt.timedelta(days=1): continue
   host=urllib.parse.urlparse(link).hostname or ''
   if not host or host.endswith('.ru') or not link.startswith('https://'): continue
   try:
    with urllib.request.urlopen(urllib.request.Request(link,headers={'User-Agent':'Mozilla/5.0'},method='HEAD'),timeout=8) as r: link=r.geturl()
   except Exception: continue
   host=urllib.parse.urlparse(link).hostname or ''
   if not host or host.endswith('.ru'): continue
   out.append(dict(title=title,summary=desc,url=link,source=host,date=stamp.isoformat()))
  return out
 except Exception as ex: print(url,ex); return []
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool: items=[i for group in pool.map(fetch,feeds) for i in group]
items.sort(key=lambda i:i['date'],reverse=True); used=set(); sections=[[] for _ in queries]
for n in [3,2,5,4,1,0]:
 for i in items:
  if len(sections[n])>=5: break
  if i['url'] in used or not re.search(keywords[n],i['title']+' '+i['summary'],re.I): continue
  sections[n].append(i); used.add(i['url'])
if not items: raise SystemExit('No verified fresh RSS entries; preserving previous edition')
key=now.date().isoformat(); (archive/(key+'.json')).write_text(json.dumps({'date':key,'updated':now.isoformat(),'sections':sections},ensure_ascii=False),encoding='utf8')
for p in archive.glob('*.json'):
 if p.stem < (now.date()-dt.timedelta(days=29)).isoformat(): p.unlink()
(root/'editions.json').write_text(json.dumps(sorted([p.stem for p in archive.glob('*.json')],reverse=True)))
