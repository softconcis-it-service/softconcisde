#!/usr/bin/env python3
"""Generiert die News-Seiten der statischen Website aus Sanity.

Aufruf:  python3 cms/build/generate.py   (aus dem Repo-Root)

Erzeugt/aktualisiert:
- alle Artikelseiten  /<slug>/index.html  bzw.  /en/<slug>/index.html
- die News-Übersicht  /unternehmen/news/ (+ /page/N/), DE und EN
- die 3 News-Teaser auf der Startseite (DE + EN)
- lädt neue Sanity-Bilder nach /assets/media/cms/ herunter

Löscht Artikel-Ordner, deren Beitrag in Sanity nicht mehr existiert
(Buchführung in cms/build/manifest.json).
"""

import hashlib
import html as htmllib
import json
import re
import shutil
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# python.org-Python bringt keine CA-Zertifikate mit; macOS-Bundle verwenden
if Path('/etc/ssl/cert.pem').exists():
    _ctx = ssl.create_default_context(cafile='/etc/ssl/cert.pem')
    urllib.request.install_opener(
        urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx)))

ROOT = Path(__file__).resolve().parent.parent.parent
TPL = Path(__file__).resolve().parent / 'templates'
MANIFEST = Path(__file__).resolve().parent / 'manifest.json'
ASSET_DIR = ROOT / 'assets' / 'media' / 'cms'

PROJECT = 'jwrq46c6'
DATASET = 'production'
PER_PAGE = 3
TZ = ZoneInfo('Europe/Berlin')

# Absolute Basis-URL für die `link`-Felder des WP-REST-Feeds (siehe build_feed).
# Muss die Live-Domain bleiben — die WebCIS-Software verlinkt damit direkt auf
# die Beiträge („weiterhin WordPress-Link").
SITE = 'https://www.softconcis.de'

MONTHS = {
    'de': ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
           'August', 'September', 'Oktober', 'November', 'Dezember'],
    'en': ['January', 'February', 'March', 'April', 'May', 'June', 'July',
           'August', 'September', 'October', 'November', 'December'],
}
LABELS = {
    'de': {'prev': 'Zurück', 'next': 'Vor', 'more': 'Weiterlesen',
           'base': '/unternehmen/news/'},
    'en': {'prev': 'Previous', 'next': 'Next', 'more': 'Read More',
           'base': '/en/unternehmen/news/'},
}

QUERY = """*[_type=='post' && defined(slug.current)]|order(publishedAt desc){
  _id, title, 'slug': slug.current, language, publishedAt, author, excerpt,
  seoTitle, seoDescription,
  'translation': translation->{_id, 'slug': slug.current, 'language': language},
  body[]{..., _type=='image'=>{'url': asset->url,
    'width': asset->metadata.dimensions.width,
    'height': asset->metadata.dimensions.height}}
}"""


def esc(s):
    return htmllib.escape(s or '', quote=False)


def esc_attr(s):
    return htmllib.escape(s or '', quote=True)


def fetch_posts():
    url = (f'https://{PROJECT}.api.sanity.io/v2024-01-01/data/query/{DATASET}'
           f'?query={urllib.parse.quote(QUERY)}&perspective=published')
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.load(r)
    posts = data['result']
    for p in posts:
        dt = datetime.fromisoformat(p['publishedAt'].replace('Z', '+00:00')).astimezone(TZ)
        p['_dt'] = dt
        p['_iso'] = dt.isoformat()
        lang = p.get('language') or 'de'
        p['language'] = 'en' if lang == 'en' else 'de'
        p['_display'] = f'{dt.day}. {MONTHS[p["language"]][dt.month - 1]} {dt.year}'
        p['_url'] = ('/en/' if p['language'] == 'en' else '/') + p['slug'] + '/'
        p['_pid'] = int(hashlib.md5(p['_id'].encode()).hexdigest()[:6], 16) % 90000 + 10000
        p['author'] = p.get('author') or 'Softconcis-News'

    # Übersetzungs-URL symmetrisch auflösen: eine Verknüpfung in eine Richtung
    # genügt; Fallback ist ein identischer Slug in der anderen Sprache.
    by_id = {p['_id']: p for p in posts}
    for p in posts:
        p['_tr_url'] = None
    for p in posts:
        tr = p.get('translation')
        if tr and tr.get('slug') and tr.get('language') and tr['language'] != p['language']:
            p['_tr_url'] = ('/en/' if tr['language'] == 'en' else '/') + tr['slug'] + '/'
            other = by_id.get(tr.get('_id'))
            if other and not other['_tr_url']:
                other['_tr_url'] = p['_url']
    for p in posts:
        if not p['_tr_url']:
            for q in posts:
                if q['language'] != p['language'] and q['slug'] == p['slug']:
                    p['_tr_url'] = q['_url']
                    break
    return posts


def author_slug(name):
    s = name.lower()
    for a, b in [('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')]:
        s = s.replace(a, b)
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', s)).strip('-') or 'softconcis-news'


def download_image(url):
    """Lädt ein Sanity-Bild einmalig nach /assets/media/cms/ und liefert den lokalen Pfad."""
    name = url.rsplit('/', 1)[-1]
    target = ASSET_DIR / name
    if not target.exists():
        ASSET_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r:
            target.write_bytes(r.read())
        print(f'  Bild heruntergeladen: {name}')
    return f'/assets/media/cms/{name}'


def plain_text(body):
    out = []
    for b in body or []:
        if b.get('_type') == 'block':
            out.append(''.join(c.get('text', '') for c in b.get('children', [])))
    return ' '.join(' '.join(out).split())


def excerpt_text(post, words=10):
    if post.get('excerpt'):
        return ' '.join(post['excerpt'].split())
    w = plain_text(post.get('body')).split()
    return ' '.join(w[:words]) + (' [...]' if len(w) > words else '')


def meta_description(post):
    if post.get('seoDescription'):
        return post['seoDescription']
    w = plain_text(post.get('body')).split()
    return ' '.join(w[:28])


# ---------------------------------------------------------------- Portable Text -> HTML

def render_spans(block):
    defs = {d['_key']: d for d in block.get('markDefs', [])}
    out = []
    for child in block.get('children', []):
        text = esc(child.get('text', '')).replace('\n', '<br />\n')
        deco, links = [], []
        for m in child.get('marks', []):
            (links if m in defs else deco).append(m)
        for m in sorted(deco):  # em, strong, underline – stabile Reihenfolge
            tag = {'strong': 'strong', 'em': 'em', 'underline': 'u'}.get(m)
            if tag:
                text = f'<{tag}>{text}</{tag}>'
        for key in links:
            d = defs[key]
            extra = ' target="_blank" rel="noopener"' if d.get('blank') else ''
            text = f'<a href="{esc_attr(d.get("href", "#"))}"{extra}>{text}</a>'
        out.append(text)
    return ''.join(out)


def render_body(body):
    out = []
    list_stack = []  # offene Listen: 'ul' / 'ol'

    def close_lists(to_level=0):
        while len(list_stack) > to_level:
            out.append(f'</li>\n</{list_stack.pop()}>')
        if list_stack:
            out.append('</li>')

    for b in body or []:
        t = b.get('_type')
        if t == 'block' and b.get('listItem'):
            tag = 'ul' if b['listItem'] == 'bullet' else 'ol'
            level = b.get('level', 1)
            if len(list_stack) < level:
                out.append(f'<{tag}>')
                list_stack.append(tag)
            else:
                close_lists(level)
                if not list_stack:
                    out.append(f'<{tag}>')
                    list_stack.append(tag)
                else:
                    out.append('')
            out.append(f'<li>{render_spans(b)}')
            continue
        close_lists(0)
        if t == 'block':
            style = b.get('style') or 'normal'
            inner = render_spans(b)
            if style == 'blockquote':
                out.append(f'<blockquote><p>{inner}</p></blockquote>')
            elif style in ('h2', 'h3', 'h4', 'h5', 'h6'):
                out.append(f'<{style}>{inner}</{style}>')
            else:
                out.append(f'<p>{inner}</p>')
        elif t == 'image' and b.get('url'):
            src = download_image(b['url'])
            dim = ''
            if b.get('width') and b.get('height'):
                dim = f' width="{int(b["width"])}" height="{int(b["height"])}"'
            alt = esc_attr(b.get('alt') or '')
            out.append(f'<p><img decoding="async" src="{src}" alt="{alt}"{dim} class="aligncenter" /></p>')
        elif t == 'htmlEmbed' and b.get('html'):
            out.append(b['html'])
    close_lists(0)
    return '\n' + '\n'.join(x for x in out if x) + '\n'


# ---------------------------------------------------------------- HTML-Bausteine

def replace_div_inner(html, open_pattern, new_inner):
    """Ersetzt den Inhalt des ersten div, dessen Öffnungs-Tag auf open_pattern passt."""
    m = re.search(open_pattern, html)
    if not m:
        raise RuntimeError(f'Marker nicht gefunden: {open_pattern}')
    start = m.end()
    depth = 1
    for tag in re.finditer(r'<(/?)div\b', html[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return html[:start] + new_inner + html[start + tag.start():]
    raise RuntimeError(f'Kein schließendes div für: {open_pattern}')


def meta_info_html(post):
    return (f'<div class="sc-meta-info"><div class="sc-meta-info-wrapper">'
            f'<span class="vcard rich-snippet-hidden"><span class="fn">'
            f'<a href="/author/{author_slug(post["author"])}/" rel="author">{esc(post["author"])}</a></span></span>'
            f'<span class="updated rich-snippet-hidden">{post["_iso"]}</span>'
            f'<span>{post["_display"]}</span><span class="sc-inline-sep">|</span></div></div>')


def card_html(post, lang):
    url, title = post['_url'], esc(post['title'])
    return f'''<article id="blog-1-post-{post['_pid']}" class="sc-post-grid post-{post['_pid']} post type-post status-publish format-standard hentry category-nicht-kategorisiert-2">
<div class="sc-post-wrapper" style="background-color:rgba(255,255,255,0);border:1px solid var(--scb-color2);border-bottom-width:3px;">
<div class="sc-post-content-wrapper" style="padding:30px 25px 25px 25px;"><div class="sc-post-content post-content"><div class="blog-shortcode-post-title entry-title"><a href="{url}">{title}</a></div><p class="sc-single-line-meta"><span class="vcard" style="display: none;"><span class="fn"><a href="/author/{author_slug(post['author'])}/" rel="author">{esc(post['author'])}</a></span></span><span class="updated" style="display:none;">{post['_iso']}</span><span>{post['_display']}</span><span class="sc-inline-sep">|</span></p><div class="sc-content-sep sep-double sep-solid"></div><div class="sc-post-content-container"><p>{esc(excerpt_text(post))}</p></div></div><div class="sc-meta-info"><div class="sc-alignleft"><a class="sc-read-more" href="{url}">{LABELS[lang]['more']}<span class="screen-reader-text">: {title}</span></a></div></div></div><div class="sc-clearfix"></div></div>
</article>'''


def sidebar_items(posts, lang, current_url=None):
    items = []
    for p in [x for x in posts if x['language'] == lang][:5]:
        aria = ' aria-current="page"' if p['_url'] == current_url else ''
        items.append(f'\n<li>\n<a href="{p["_url"]}"{aria}>{esc(p["title"])}</a>\n'
                     f'<span class="post-date">{p["_display"]}</span>\n</li>')
    return ''.join(items) + '\n'


def pagination_html(lang, page, total):
    base = LABELS[lang]['base']
    url = lambda k: base if k == 1 else f'{base}page/{k}/'
    parts = []
    if page > 1:
        parts.append(f'<a class="pagination-prev" rel="prev" href="{url(page - 1)}">'
                     f'<span class="page-prev"></span><span class="page-text">{LABELS[lang]["prev"]}</span></a>')
    for k in range(max(1, page - 1), min(total, page + 1) + 1):
        if k == page:
            parts.append(f'<span class="current">{k}</span>')
        else:
            parts.append(f'<a href="{url(k)}" class="inactive">{k}</a>')
    if page < total:
        parts.append(f'<a class="pagination-next" rel="next" href="{url(page + 1)}">'
                     f'<span class="page-text">{LABELS[lang]["next"]}</span><span class="page-next"></span></a>')
    return ''.join(parts)


# ---------------------------------------------------------------- Seiten-Generierung

def scl_switcher(post, posts, lang):
    url = post.get('_tr_url')
    if not url:
        return ''
    snips = json.loads((TPL / 'scl-snippets.json').read_text(encoding='utf-8'))
    snippet = snips[lang]
    old_href = '/en/webcis-roboadvisor/' if lang == 'de' else '/webcis-roboadvisor/'
    return snippet.replace(f'href="{old_href}"', f'href="{url}"')


def render_article(post, posts, lang):
    tpl = (TPL / f'article-{lang}.html').read_text(encoding='utf-8')
    same = [p for p in posts if p['language'] == lang]
    i = same.index(post)
    newer = same[i - 1] if i > 0 else None            # Liste ist absteigend sortiert
    older = same[i + 1] if i + 1 < len(same) else None

    title_tag = post.get('seoTitle') or f'{post["title"]} - SOFTCON CIS'
    html = tpl

    # <title> + genau eine Meta-Description direkt danach
    html = re.sub(r'<meta name="description" content=".*?"\s*/>\n?', '', html, flags=re.S)
    html = re.sub(r'<title>.*?</title>',
                  lambda _: f'<title>{esc(title_tag)}</title>\n'
                            f'<meta name="description" content="{esc_attr(meta_description(post))}" />',
                  html, count=1, flags=re.S)
    html = re.sub(r"<link rel='shortlink'[^>]*/>\n?", '', html)
    html = re.sub(r'(<meta name="author" content=")[^"]*(")',
                  lambda m: m.group(1) + esc_attr(post['author']) + m.group(2), html)

    # Sprachumschalter (Flagge) im Hauptmenü, wenn eine Übersetzung existiert
    switcher = scl_switcher(post, posts, lang)
    if switcher:
        html = html.replace('</ul></nav>', switcher + '</ul></nav>', 1)

    # Post-IDs (nur kosmetisch, CSS-Klassen)
    html = re.sub(r'postid-\d+', f'postid-{post["_pid"]}', html)
    html = re.sub(r'data-scb-post-id="\d+"', f'data-scb-post-id="{post["_pid"]}"', html)
    html = re.sub(r'<article id="post-\d+" class="post post-\d+',
                  f'<article id="post-{post["_pid"]}" class="post post-{post["_pid"]}', html)

    # Navigation Zurück/Vor (chronologisch)
    nav = ''
    if older:
        nav += f'\n<a href="{older["_url"]}" rel="prev">{LABELS[lang]["prev"]}</a>\t\t\t'
    if newer:
        nav += f'<a href="{newer["_url"]}" rel="next">{LABELS[lang]["next"]}</a>\t\t'
    html = re.sub(r'(<div class="single-navigation clearfix">).*?(</div>)',
                  lambda m: m.group(1) + nav + m.group(2), html, count=1, flags=re.S)

    # Titel + Inhalt
    html = re.sub(r'<h1 class="entry-title sc-post-title">.*?</h1>',
                  lambda _: f'<h1 class="entry-title sc-post-title">{esc(post["title"])}</h1>',
                  html, count=1, flags=re.S)
    html = replace_div_inner(html, r'<div class="post-content">', render_body(post.get('body')))

    # Accessibility-Plugin-Konfiguration (var wpa) auf diesen Beitrag umstellen
    html = re.sub(r'("url":")[^"]*(","post_id":")\d+(")',
                  lambda m: m.group(1) + post['_url'] + m.group(2) + str(post['_pid']) + m.group(3),
                  html, count=1)

    # Meta-Zeile unter dem Artikel
    html = re.sub(r'<div class="sc-meta-info"><div class="sc-meta-info-wrapper">.*?</div></div>',
                  lambda _: meta_info_html(post), html, count=1, flags=re.S)

    # Sidebar „Neueste Beiträge“
    html = re.sub(r'(<section id="recent-posts-\d+".*?<ul>).*?(</ul>)',
                  lambda m: m.group(1) + sidebar_items(posts, lang, post['_url']) + m.group(2),
                  html, count=1, flags=re.S)
    return html


def render_listing(posts, lang, page, total):
    tpl = (TPL / f'list-{lang}.html').read_text(encoding='utf-8')
    subset = [p for p in posts if p['language'] == lang][(page - 1) * PER_PAGE: page * PER_PAGE]
    cards = '\n'.join(card_html(p, lang) for p in subset)
    html = re.sub(r'(<div class="sc-posts-container[^>]*data-pages=")\d+(")',
                  lambda m: m.group(1) + str(total) + m.group(2), tpl)
    html = replace_div_inner(html, r'<div class="sc-posts-container[^>]*>',
                             cards + '\n<div class="sc-clearfix"></div>')
    html = re.sub(r'<div class="pagination clearfix">.*?</div>',
                  lambda _: f'<div class="pagination clearfix">{pagination_html(lang, page, total)}</div>',
                  html, count=1, flags=re.S)
    return html


# Inline-CSS/JS für den News-Slider — bewusst nur auf der News-Übersichtsseite
# (kein Extra-Asset, HTML wird ohnehin no-cache ausgeliefert). Macht aus der
# 3-Spalten-Kartenreihe ein Karussell, das per Vor/Zurück dynamisch um genau
# einen Beitrag weiterschiebt (kein Seiten-Reload).
NEWS_SLIDER_ASSETS = """
<style id="sc-newsslider-css">
.sc-newsslider-viewport{overflow:hidden;width:100%;touch-action:pan-y}
/* Theme-Masonry (Isotope) neutralisieren: es setzt Inline-position:absolute auf
   die Karten und eine feste Container-Höhe -> mit !important zurückholen. */
.sc-posts-container{height:auto!important;position:static!important}
.sc-newsslider-track{display:flex;flex-wrap:nowrap;align-items:stretch;transition:transform .5s cubic-bezier(.16,.84,.44,1);will-change:transform}
.sc-newsslider-track>.sc-post-grid{flex:0 0 33.3333%;max-width:33.3333%;float:none!important;position:static!important;left:auto!important;top:auto!important;transform:none!important;margin-bottom:0!important}
/* Karten exakt wie auf der Startseite (natürlicher Theme-Weißraum, flex-grow,
   50px vor "Weiterlesen"). Titel nur bei 5 Zeilen kappen — das ist die
   natürliche Maximalhöhe der Startseite; nötig, weil im Slider alle 74 Beiträge
   liegen und ein einzelner überlanger Titel die Einheitshöhe sonst höher als
   auf der Startseite triebe. Anriss unbegrenzt wie auf der Startseite. */
.sc-newsslider-track .blog-shortcode-post-title a{display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden}
.sc-newsslider-track .sc-post-content-container p{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;margin:0}
@media (max-width:979px){.sc-newsslider-track>.sc-post-grid{flex-basis:50%;max-width:50%}}
@media (max-width:679px){.sc-newsslider-track>.sc-post-grid{flex-basis:100%;max-width:100%}}
/* Mobil (eine Karte sichtbar): auf Extra-Weißraum verzichten -> kein flex-grow,
   kleiner Abstand vor "Weiterlesen", natürliche Höhe (die Viewport-Höhe folgt
   per JS der aktuellen Karte). */
@media (max-width:679px){
  .sc-newsslider-track{align-items:flex-start}
  .sc-newsslider-track .sc-post-content-wrapper{flex-grow:0!important}
  .sc-newsslider-track .sc-post-content{margin-bottom:6px!important}
  .sc-newsslider-track .sc-meta-info{padding-top:12px!important}
}
.sc-newsslider-nav{display:flex;gap:30px;justify-content:center;align-items:center;margin-top:8px}
.sc-newsslider-nav .sc-ns-btn{display:inline-flex;align-items:center;gap:8px;background:none;border:0;cursor:pointer;font:inherit;font-weight:600;color:#fff!important;padding:8px 4px;transition:color .2s ease}
.sc-newsslider-nav .sc-ns-ico{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;transition:transform .2s ease}
.sc-newsslider-nav .sc-ns-btn:not([disabled]):hover,.sc-newsslider-nav .sc-ns-btn:not([disabled]):focus-visible{color:#eee!important}
.sc-newsslider-nav .sc-ns-prev:not([disabled]):hover .sc-ns-ico{transform:translateX(-3px)}
.sc-newsslider-nav .sc-ns-next:not([disabled]):hover .sc-ns-ico{transform:translateX(3px)}
.sc-newsslider-nav .sc-ns-btn[disabled]{opacity:.55;cursor:default}
@media (prefers-reduced-motion:reduce){.sc-newsslider-track{transition:none}}
</style>
<script id="sc-newsslider-js">
(function(){
  var track=document.querySelector('.sc-newsslider-track');
  if(!track) return;
  var viewport=track.parentNode;
  var cards=Array.prototype.slice.call(track.children);
  if(!cards.length) return;
  var prev=document.querySelector('.sc-ns-prev'), next=document.querySelector('.sc-ns-next');
  var index=0;
  function cardW(){ return cards[0].getBoundingClientRect().width; }
  function perView(){ var w=cardW(); return w?Math.max(1,Math.round(viewport.getBoundingClientRect().width/w)):1; }
  function maxIndex(){ return Math.max(0, cards.length-perView()); }
  function setX(px,animate){ track.style.transition=animate?'':'none'; track.style.transform='translateX('+px+'px)'; }
  function apply(){
    index=Math.min(Math.max(index,0),maxIndex());
    setX(-index*cardW(),true);
    if(prev) prev.disabled=index<=0;
    if(next) next.disabled=index>=maxIndex();
    // Mobil (nur eine Karte sichtbar): Viewport-Höhe an die aktuelle Karte
    // anpassen, damit kein Leerraum unter kürzeren Beiträgen entsteht.
    if(perView()<=1 && cards[index]){ viewport.style.height=Math.round(cards[index].getBoundingClientRect().height)+'px'; }
    else { viewport.style.height=''; }
  }
  function step(d){ index+=d; apply(); }
  if(prev) prev.addEventListener('click',function(){step(-1);});
  if(next) next.addEventListener('click',function(){step(1);});
  var rt; window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(apply,150);});

  /* Finger-Wischen (Touch): horizontal folgen, beim Loslassen um einen Beitrag weiter */
  var sx=0,sy=0,base=0,drag=false,lock=null;
  viewport.addEventListener('touchstart',function(e){
    if(e.touches.length!==1) return;
    sx=e.touches[0].clientX; sy=e.touches[0].clientY; base=-index*cardW(); drag=true; lock=null;
  },{passive:true});
  viewport.addEventListener('touchmove',function(e){
    if(!drag) return;
    var dx=e.touches[0].clientX-sx, dy=e.touches[0].clientY-sy;
    if(lock===null) lock=Math.abs(dx)>Math.abs(dy)?'h':'v';
    if(lock==='v') return;
    e.preventDefault();
    setX(base+dx,false);
  },{passive:false});
  viewport.addEventListener('touchend',function(e){
    if(!drag) return; drag=false;
    if(lock!=='h') return;
    var dx=e.changedTouches[0].clientX-sx, thr=Math.max(40,cardW()*0.2);
    if(dx<=-thr) index++; else if(dx>=thr) index--;
    apply();
  });

  /* Trackpad: horizontales Zwei-Finger-Wischen (ein Schritt pro Wisch) */
  var accum=0,cool=false;
  viewport.addEventListener('wheel',function(e){
    if(Math.abs(e.deltaX)<=Math.abs(e.deltaY)) return;
    e.preventDefault();
    if(cool) return;
    accum+=e.deltaX;
    if(accum<=-40||accum>=40){ step(accum<0?-1:1); accum=0; cool=true; setTimeout(function(){cool=false;},450); }
  },{passive:false});

  apply();
})();
</script>
"""


def render_news_slider(posts, lang):
    """News-Übersicht als 3er-Karussell: ALLE Beiträge liegen im DOM, Vor/Zurück
    slidet dynamisch um je einen Beitrag weiter (kein Reload, keine Pagination)."""
    tpl = (TPL / f'list-{lang}.html').read_text(encoding='utf-8')
    items = [p for p in posts if p['language'] == lang]
    cards = '\n'.join(card_html(p, lang) for p in items)
    html = re.sub(r'(<div class="sc-posts-container[^>]*data-pages=")\d+(")',
                  lambda m: m.group(1) + '1' + m.group(2), tpl)
    # Das Theme-Masonry (Isotope) positioniert die Karten absolut und würde den
    # Flex-Slider aushebeln -> die auslösenden Klassen am Container entfernen,
    # damit die Karten normal im Track fließen.
    html = re.sub(r'(<div class="sc-posts-container[^"]*?)\s*\bisotope\b',
                  r'\1', html, count=1)
    track = ('<div class="sc-newsslider-viewport"><div class="sc-newsslider-track">'
             + cards + '</div></div>')
    html = replace_div_inner(html, r'<div class="sc-posts-container[^>]*>',
                             track + '\n<div class="sc-clearfix"></div>')
    chevron_l = ('<svg class="sc-ns-ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
                 '<path d="M14 5l-4 7 4 7"/></svg>')
    chevron_r = ('<svg class="sc-ns-ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
                 '<path d="M10 5l4 7-4 7"/></svg>')
    nav = (f'<button type="button" class="sc-ns-btn sc-ns-prev" aria-label="{LABELS[lang]["prev"]}" disabled>'
           f'{chevron_l}<span class="page-text">{LABELS[lang]["prev"]}</span></button>'
           f'<button type="button" class="sc-ns-btn sc-ns-next" aria-label="{LABELS[lang]["next"]}">'
           f'<span class="page-text">{LABELS[lang]["next"]}</span>{chevron_r}</button>')
    html = re.sub(r'<div class="pagination clearfix">.*?</div>',
                  lambda _: f'<div class="pagination clearfix sc-newsslider-nav">{nav}</div>',
                  html, count=1, flags=re.S)
    return html.replace('</body>', NEWS_SLIDER_ASSETS + '</body>', 1)


def update_homepage(path, posts, lang):
    html = path.read_text(encoding='utf-8')
    subset = [p for p in posts if p['language'] == lang][:3]
    cards = '\n'.join(card_html(p, lang) for p in subset)
    total = -(-len([p for p in posts if p['language'] == lang]) // PER_PAGE)
    html = re.sub(r'(<div class="sc-posts-container[^>]*data-pages=")\d+(")',
                  lambda m: m.group(1) + str(total) + m.group(2), html)
    html = replace_div_inner(html, r'<div class="sc-posts-container[^>]*>',
                             cards + '\n<div class="sc-clearfix"></div>')
    path.write_text(html, encoding='utf-8')


# ---------------------------------------------------------------- WP-REST-Feed
# Die WebCIS-Software von Softconcis liest die Blogposts über den WordPress-
# REST-Feed /wp-json/wp/v2/posts. Nach der Sanity-Umstellung bilden wir diesen
# Feed als statisches JSON originalgetreu nach (gleiche URL per .htaccess-
# Rewrite). Die Software liest daraus title.rendered, date, excerpt.rendered
# und link — diese vier werden formattreu erzeugt; date_gmt/slug/status/type
# kommen als korrekte WP-Standardfelder dazu.

def wp_excerpt(post):
    """excerpt.rendered im WordPress-Format.

    WordPress generiert den Anriss automatisch aus dem Beitragsanfang
    (erste 10 Wörter + '  [&#8230;]', in <p>…</p> gehüllt). Ein manuell in
    Sanity gepflegter Anriss-Text wird — wie in WordPress — ohne Kürzungs-
    marker ausgegeben.
    """
    manual = post.get('excerpt')
    if manual and manual.strip():
        return f'<p>{esc(" ".join(manual.split()))}</p>\n'
    words = plain_text(post.get('body')).split()
    return f'<p>{esc(" ".join(words[:10]))}  [&#8230;]</p>\n'


def wp_post(post):
    dt = post['_dt']
    return {
        'id': post['_pid'],
        'date': dt.strftime('%Y-%m-%dT%H:%M:%S'),
        'date_gmt': dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
        'slug': post['slug'],
        'status': 'publish',
        'type': 'post',
        'link': SITE + post['_url'],
        'title': {'rendered': esc(post['title'])},
        'excerpt': {'rendered': wp_excerpt(post)},
    }


def build_feed(path, posts):
    """Schreibt die Postliste (bereits nach Datum absteigend sortiert) als
    statisches WP-REST-JSON. Rohes UTF-8 wie der originale Live-Feed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [wp_post(p) for p in posts]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return len(data)


def main():
    print('Hole Beiträge aus Sanity …')
    posts = fetch_posts()
    de = [p for p in posts if p['language'] == 'de']
    en = [p for p in posts if p['language'] == 'en']
    print(f'{len(posts)} Beiträge ({len(de)} DE, {len(en)} EN)')

    generated = []

    # Artikelseiten
    for post in posts:
        rel = ('en/' if post['language'] == 'en' else '') + post['slug']
        out = ROOT / rel / 'index.html'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_article(post, posts, post['language']), encoding='utf-8')
        generated.append(rel)

    # News-Übersicht: dynamischer 3er-Slider (alle Beiträge im DOM, Vor/Zurück
    # slidet um je einen Beitrag — kein Reload, keine Pagination-Unterseiten)
    for lang in ('de', 'en'):
        base = ROOT / ('en/unternehmen/news' if lang == 'en' else 'unternehmen/news')
        base.mkdir(parents=True, exist_ok=True)
        (base / 'index.html').write_text(render_news_slider(posts, lang), encoding='utf-8')
        pages_dir = base / 'page'
        if pages_dir.exists():
            shutil.rmtree(pages_dir)
            print(f'  Alte Pagination-Unterseiten entfernt: {pages_dir.relative_to(ROOT)}')

    # Startseiten-Teaser
    update_homepage(ROOT / 'index.html', posts, 'de')
    update_homepage(ROOT / 'en/index.html', posts, 'en')

    # WP-REST-Feed für die WebCIS-Software (gleiche URL wie früher, per Rewrite)
    n_de = build_feed(ROOT / 'wp-json' / 'wp' / 'v2' / 'posts.json', de)
    n_en = build_feed(ROOT / 'en' / 'wp-json' / 'wp' / 'v2' / 'posts.json', en)
    print(f'WP-Feed geschrieben: {n_de} DE + {n_en} EN Posts.')

    # Gelöschte Beiträge aufräumen
    old = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    for rel in old:
        if rel not in generated and re.fullmatch(r'(en/)?[a-z0-9-]+', rel) and (ROOT / rel).exists():
            shutil.rmtree(ROOT / rel)
            print(f'  Beitrag gelöscht: {rel}')
    MANIFEST.write_text(json.dumps(sorted(generated), indent=1))

    n_pages = len(generated) + 4
    print(f'Fertig: {len(posts)} Artikelseiten, Listings (DE {-(-len(de) // PER_PAGE)} Seiten, '
          f'EN {-(-len(en) // PER_PAGE)} Seiten), 2 Startseiten aktualisiert.')


if __name__ == '__main__':
    sys.exit(main())
