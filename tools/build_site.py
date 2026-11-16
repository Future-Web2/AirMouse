"""Builds the AirMouse website into site/: a static landing page in Russian and English.

    python tools/build_site.py            -> site/index.html (Russian) and site/en/index.html (English)
    python tools/build_site.py --assets   -> also rebuilds site/assets/ from promo/ and docs/

The site/ folder is the whole website: static files for any hosting. On Railway it is a service with
Root Directory /site: Railway sees index.html (and site/Staticfile) and serves the folder as it is.
The words are in tools/site_texts.py, the look in site/styles.css, the behaviour in site/app.js.

--assets needs the commercials (promo/AirMouse_ad.mp4, promo/AirMouse_ad_en.mp4): it makes
1280x720 copies for the web, their first pictures, the screenshots as WebP and the icons.

When the site gets its address, put it in SITE_URL (canonical links, the sitemap, the preview
picture for messengers) and in CTA_URL of promo/make_ad.py, then build and render again.
"""

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SITE = ROOT / "site"
ASSETS = SITE / "assets"
sys.path.insert(0, str(HERE))

from site_texts import T  # noqa: E402

# -- what the owner decides ------------------------------------------------------------------
SITE_URL = "https://airmouse.veranix.xyz"   # no slash at the end; "" builds a site without an address
VERSION = "1.7.0"        # the release the download buttons give
FREE = True              # the page says "free" (the hero, the FAQ, the last call)
PRO = True               # the "free and Pro" block: Pro is announced, with no list of features and no price yet
SUPPORT = {"Boosty": "", "Ko-fi": ""}       # donation pages; a button appears when its link is filled in
TELEGRAM = "https://t.me/veranix1"          # news and questions; "" hides the links

REPO = "https://github.com/Future-Web2/AirMouse"
WIN_URL = REPO + "/releases/latest/download/AirMouse-windows-x64.zip"
LINUX_URL = REPO + "/releases/latest/download/AirMouse-linux-x64.tar.gz"
RELEASES = REPO + "/releases"
ISSUES = REPO + "/issues"
KPI = REPO + "/blob/main/docs/KPI.md"
VIDEO_GUIDE = REPO + "/blob/main/promo/AirMouse_guide.mp4"
GUIDE = (REPO + "/blob/main/docs/GUIDE.md", REPO + "/blob/main/docs/GUIDE.en.md")
LINUX_HELP = (REPO + "#linux", REPO + "/blob/main/README.en.md#linux")

LANGS = ("ru", "en")

# -- icons: 24x24 line drawings ----------------------------------------------------------------
ICONS = {
    "hand": '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V11m0-1V4a1.5 1.5 0 0 1 3 0v7m0-5.5a1.5 1.5 0 0 1 3 0V13'
            'm0-3a1.5 1.5 0 0 1 3 0v5a7 7 0 0 1-7 7h-1a7 7 0 0 1-5.6-2.8L3.6 15a1.6 1.6 0 0 1 2.5-2L8 15"/>',
    "screen": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "pulse": '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "shield": '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8-7.5 9.5-4.3-1.5-7.5-4.9-7.5-9.5V6z"/><path d="M9 12l2.2 2.2L15.2 10"/>',
    "wifi_off": '<path d="M3 3l18 18M8.5 16.3a5 5 0 0 1 7 0M5.2 12.8a9.5 9.5 0 0 1 4.300-2.400M13.500 9.800a9.500 9.500 0 0 1 5.300 3'
                'M2 9.300a14.500 14.500 0 0 1 4.200-2.700M10.300 4.700A14.500 14.500 0 0 1 22 9.300"/><circle cx="12" cy="19.500" r="0.800"/>',
    "user_off": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0M3 3l18 18"/>',
    "code": '<path d="M8.500 7.500L4 12l4.500 4.500M15.500 7.500L20 12l-4.500 4.500M13.500 5l-3 14"/>',
    "folder": '<path d="M3.500 7a2 2 0 0 1 2-2h4l2 2.500h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "download": '<path d="M12 4v11m0 0l-4.500-4.500M12 15l4.500-4.500M5 19.500h14"/>',
    "play": '<path d="M8 5.500v13l11-6.500z" fill="currentColor"/>',
    "arrow": '<path d="M5 12h14m0 0l-5.500-5.500M19 12l-5.500 5.500"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "palette": '<rect x="3.500" y="3.500" width="7" height="7" rx="1.800"/><rect x="13.500" y="3.500" width="7" height="7" rx="1.800"/>'
               '<rect x="3.500" y="13.500" width="7" height="7" rx="1.800"/><rect x="13.500" y="13.500" width="7" height="7" rx="1.800"/>',
    "sliders": '<path d="M4 7h9m4 0h3M4 12h3m4 0h9M4 17h11m4 0h1"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/>'
               '<circle cx="17" cy="17" r="2"/>',
    "bolt": '<path d="M13 3L5 13.500h6L10 21l8.500-11h-6z"/>',
    "globe": '<circle cx="12" cy="12" r="8.500"/><path d="M3.500 12h17M12 3.500c2.500 2.300 3.800 5.200 3.800 8.500s-1.300 6.200-3.800 8.500'
             'c-2.500-2.300-3.800-5.200-3.800-8.500S9.500 5.800 12 3.500z"/>',
    "windows": '<path d="M3 5.500l7.500-1v7H3zM11.500 4.300L21 3v8.500h-9.500zM3 12.500h7.500v7L3 18.500zM11.500 12.500H21V21l-9.500-1.300z" '
               'fill="currentColor" stroke="none"/>',
    "linux": '<rect x="3" y="4.500" width="18" height="15" rx="2.500"/><path d="M7 10l3 2.500L7 15M12.500 15H17"/>',
    "github": '<path d="M12 2.500a9.500 9.500 0 0 0-3 18.500c.5.100.700-.200.700-.500v-1.700c-2.700.600-3.200-1.300-3.200-1.300-.400-1.100-1.100-1.400-1.100-1.400'
              '-.900-.600.100-.600.100-.600 1 .100 1.500 1 1.500 1 .900 1.500 2.300 1.100 2.900.800.100-.600.300-1.100.600-1.300-2.100-.200-4.400-1.100-4.400-4.700'
              ' 0-1 .400-1.900 1-2.600-.100-.200-.400-1.200.100-2.500 0 0 .800-.300 2.600 1a9 9 0 0 1 4.800 0c1.800-1.300 2.600-1 2.600-1 .500 1.300.200 2.300.100 2.500'
              '.600.700 1 1.600 1 2.600 0 3.600-2.200 4.400-4.400 4.700.400.300.700.900.700 1.800v2.700c0 .300.200.600.700.500A9.500 9.500 0 0 0 12 2.500z" '
              'fill="currentColor" stroke="none"/>',
}


def icon(name, cls="ic"):
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.700" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


# -- the hand, as airmouse/bench.py draws it -----------------------------------------------------
HAND_LINES = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
              (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17))


def hand(pinch=0.0, pose="open", ox=112, oy=96):
    """The 21 hand points (bench.hand without z); the same formula is in site/app.js."""
    mcp = {5: (ox - 50, oy + 5), 9: (ox, oy), 13: (ox + 50, oy + 5), 17: (ox + 95, oy + 15)}
    folded = {13, 17} if pose == "two" else set()
    pts = [None] * 21
    pts[0] = (ox, oy + 100)
    for i, (mx, my) in mcp.items():
        for k, off in enumerate((0, -30, -15, 10) if i in folded else (0, -40, -65, -90)):
            pts[i + k] = (mx, my + off)
    pts[1], pts[2], pts[3] = (ox - 60, oy + 80), (ox - 85, oy + 55), (ox - 100, oy + 30)
    tip, away = (pts[8][0], pts[8][1] + 8), (ox - 110, oy + 5)
    pts[4] = (away[0] + (tip[0] - away[0]) * pinch, away[1] + (tip[1] - away[1]) * pinch)
    return pts


def hand_svg(pinch, pose):
    pts = hand(pinch, pose)
    bones = "".join(f'<line x1="{pts[a][0]:g}" y1="{pts[a][1]:g}" x2="{pts[b][0]:g}" y2="{pts[b][1]:g}"/>'
                    for a, b in HAND_LINES)
    joints = "".join(f'<circle cx="{x:g}" cy="{y:g}" r="4.200"/>' for x, y in pts)
    palm = [pts[i] for i in (0, 5, 9, 13, 17)]
    cx, cy = sum(p[0] for p in palm) / 5, sum(p[1] for p in palm) / 5
    return (f'<g class="hand"><g class="bones">{bones}</g><g class="joints">{joints}</g>'
            f'<circle class="palm" cx="{cx:g}" cy="{cy:g}" r="9"/></g>')


CURSOR = '<path class="arrow" d="M0 0v17l4.600-4.200 3.100 7.200 2.700-1.200-3.100-7.100H13.500z"/>'


def demo_svg(kind, label):
    """One gesture: the hand on the left, a small screen on the right. site/app.js makes it move."""
    pinch, pose = {"cursor": (0, "open"), "click": (0.550, "open"), "scroll": (0, "two"), "drag": (1, "open")}[kind]
    screen = {
        "cursor": '<g class="tiles"><rect x="12" y="14" width="26" height="20" rx="5"/><rect x="46" y="14" width="26" height="20" rx="5"/>'
                  '<rect x="80" y="14" width="26" height="20" rx="5"/><rect x="12" y="42" width="26" height="20" rx="5"/>'
                  '<rect x="46" y="42" width="26" height="20" rx="5"/><rect x="80" y="42" width="26" height="20" rx="5"/></g>',
        "click": '<rect class="button" x="29" y="40" width="60" height="34" rx="9"/>'
                 '<circle class="ring-bg" cx="59" cy="57" r="15"/><circle class="ring" cx="59" cy="57" r="15" pathLength="100"/>',
        "scroll": '<g class="rows">' + "".join(
            f'<rect x="14" y="{12 + 22 * i}" width="{(74, 90, 60, 82, 68, 90, 54, 78)[i]}" height="12" rx="4"/>'
            for i in range(8)) + '</g>',
        "drag": '<rect class="slot" x="12" y="42" width="34" height="30" rx="7"/><rect class="slot" x="72" y="42" width="34" height="30" rx="7"/>'
                '<rect class="tile" x="12" y="42" width="34" height="30" rx="7"/>',
    }[kind]
    at = {"cursor": (59, 48), "click": (59, 57), "scroll": (84, 60), "drag": (29, 57)}[kind]
    return (f'<svg class="demo" data-gesture="{kind}" viewBox="0 0 320 200" role="img" aria-label="{html.escape(label)}">'
            f'<g class="hand-at" transform="translate(6 26) scale(.760)">{hand_svg(pinch, pose)}</g>'
            f'<g transform="translate(190 34)"><rect class="mini" width="118" height="114" rx="14"/>'
            f'<clipPath id="clip-{kind}"><rect x="4" y="4" width="110" height="106" rx="11"/></clipPath>'
            f'<g clip-path="url(#clip-{kind})">{screen}'
            f'<g class="cursor" transform="translate({at[0]} {at[1]})">{CURSOR}</g></g></g></svg>')


def face_svg(label):
    dots = "".join(f'<circle cx="{330 + 70 * i}" cy="{70 + 62 * j}" r="{7 if (i, j) == (1, 1) else 4.500}" '
                   f'class="{"dot on" if (i, j) == (1, 1) else "dot"}"/>' for j in range(3) for i in range(3))
    return (f'<svg class="face" viewBox="0 0 520 264" role="img" aria-label="{html.escape(label)}">'
            '<rect class="mini" x="20" y="16" width="220" height="232" rx="22"/>'
            '<g class="face-lines"><ellipse cx="130" cy="132" rx="62" ry="80"/>'
            '<path d="M92 104q14-9 28 0M140 104q14-9 28 0"/>'
            '<path d="M94 122q12-11 24 0q-12 11-24 0z"/><path d="M142 123q12 7 24 0"/>'
            '<path d="M132 130l-7 26h9M110 178q20 12 40 0"/></g>'
            '<circle class="iris" cx="106" cy="122" r="5"/>'
            '<rect class="mini" x="280" y="16" width="220" height="232" rx="22"/>'
            f'{dots}<g class="cursor" transform="translate(408 138)">{CURSOR}</g>'
            '<path class="gaze" d="M196 122C250 96 300 118 392 130"/></svg>')


# -- the page ------------------------------------------------------------------------------------
class Page:
    def __init__(self, lang):
        self.lang = lang
        self.i = LANGS.index(lang)
        self.root = "" if lang == "ru" else "../"
        self.other = {"ru": "./" if lang == "ru" else "../", "en": "en/" if lang == "ru" else "./"}

    def t(self, key, *args):
        value = T[key][self.i]
        return value.format(*args) if args else value

    def asset(self, path):
        return self.root + "assets/" + path

    def img(self, path, alt, cls="", lazy=True):
        w, h = Image.open(ASSETS / path).size
        return (f'<img src="{self.asset(path)}" width="{w}" height="{h}" alt="{html.escape(alt)}"'
                f'{f" class={cls!r}" if cls else ""}{" loading=lazy decoding=async" if lazy else ""}>')

    def ext(self, url, text, cls=""):
        return f'<a{f" class={cls!r}" if cls else ""} href="{url}" target="_blank" rel="noopener">{text}</a>'

    def downloads(self, big=True):
        size = " btn-big" if big else ""
        return (f'<div class="cta-row" data-downloads>'
                f'<a class="btn btn-primary{size}" data-os="win" href="{WIN_URL}">{icon("windows")}'
                f'<span><b>{self.t("btn_win")}</b><small>{self.t("btn_win_note")}</small></span></a>'
                f'<a class="btn btn-glass{size}" data-os="linux" href="{LINUX_URL}">{icon("linux")}'
                f'<span><b>{self.t("btn_linux")}</b><small>{self.t("btn_linux_note")}</small></span></a></div>')

    # -- head --
    def head(self):
        url = f"{SITE_URL}/" if SITE_URL else ""
        here = url + ("" if self.lang == "ru" else "en/") if url else ""
        og_image = (url or self.root) + f"assets/img/og-{self.lang}.jpg"
        links = ""
        if url:
            links = (f'<link rel="canonical" href="{here}">'
                     f'<link rel="alternate" hreflang="ru" href="{url}"><link rel="alternate" hreflang="en" href="{url}en/">'
                     f'<link rel="alternate" hreflang="x-default" href="{url}en/"><meta property="og:url" content="{here}">')
        app = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "AirMouse",
               "applicationCategory": "UtilitiesApplication", "operatingSystem": "Windows 10, Windows 11, Linux",
               "softwareVersion": VERSION, "description": self.t("description"), "downloadUrl": WIN_URL,
               "inLanguage": ["ru", "en"]}
        if FREE:
            app["offers"] = {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
        if url:
            app["url"] = here
        return f"""<!doctype html>
<html lang="{self.lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{self.t("title")}</title>
<meta name="description" content="{html.escape(self.t("description"))}">
<meta name="theme-color" content="#06101f">
<meta name="color-scheme" content="dark">
{links}
<meta property="og:type" content="website">
<meta property="og:site_name" content="AirMouse">
<meta property="og:title" content="{html.escape(self.t("title"))}">
<meta property="og:description" content="{html.escape(self.t("description"))}">
<meta property="og:image" content="{og_image}">
<meta property="og:locale" content="{"ru_RU" if self.lang == "ru" else "en_US"}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{self.asset("favicon.ico")}" sizes="any">
<link rel="icon" type="image/png" sizes="192x192" href="{self.asset("icon-192.png")}">
<link rel="apple-touch-icon" href="{self.asset("icon-192.png")}">
<link rel="stylesheet" href="{self.root}styles.css">
<script>document.documentElement.className = "js"</script>
<script type="application/ld+json">{json.dumps(app, ensure_ascii=False)}</script>
</head>
"""

    def header(self):
        nav = "".join(f'<a href="#{target}">{self.t(key)}</a>' for target, key in (
            ("start", "nav_start"), ("gestures", "nav_gestures"), ("features", "nav_features"),
            ("numbers", "nav_numbers"), ("faq", "nav_faq")))
        langs = "".join(
            f'<a href="{self.other[code]}" lang="{code}" hreflang="{code}" data-lang="{code}"'
            f'{" class=on aria-current=true" if code == self.lang else ""}>{code.upper()}</a>' for code in LANGS)
        return f"""<a class="skip" href="#main">{self.t("skip")}</a>
<div class="backdrop" aria-hidden="true"><i class="orb o1"></i><i class="orb o2"></i><i class="orb o3"></i><i class="orb o4"></i></div>
<header class="top">
<div class="wrap top-in">
<a class="brand" href="#top"><img src="{self.asset("icon.png")}" width="34" height="34" alt=""><span>AirMouse</span></a>
<nav class="nav" id="nav" aria-label="{self.t("menu")}">{nav}</nav>
<div class="top-right">
<div class="lang" role="group" aria-label="{self.t("lang_label")}">{langs}</div>
<a class="btn btn-primary btn-small" href="#download">{icon("download")}<span>{self.t("nav_download")}</span></a>
<button class="burger" type="button" aria-expanded="false" aria-controls="nav" aria-label="{self.t("menu")}">{icon("menu")}</button>
</div>
</div>
</header>
"""

    def hero(self):
        chips = "".join(f"<li>{icon('check')}{c}</li>" for c in self.t("chips"))
        free = f'<b>{self.t("hero_note_free")}</b> · ' if FREE else ""
        return f"""<section class="hero" id="top">
<div class="wrap hero-in">
<p class="kicker">{self.t("hero_kicker")}</p>
<h1>{self.t("hero_h1")}</h1>
<p class="lead">{self.t("hero_sub")}</p>
{self.downloads()}
<p class="hero-note">{free}{self.t("hero_note")}</p>
<p class="phone-hint" hidden>{icon("screen")}<span>{self.t("phone_hint")}</span>
<button type="button" class="link-btn" data-copy data-done="{self.t("copied")}">{self.t("copy_link")}</button></p>
<ul class="chips">{chips}</ul>
</div>
<div class="wrap">
<figure class="film">
<div class="film-frame">
<video controls playsinline preload="none" poster="{self.asset(f"img/film-{self.lang}.jpg")}" width="1280" height="720"
 aria-label="{self.t("video_alt")}"><source src="{self.asset(f"video/airmouse-ad-{self.lang}.mp4")}" type="video/mp4"></video>
<button class="film-play" type="button"><span class="film-button">{icon("play")}</span><span>{self.t("video_play")}</span></button>
</div>
<figcaption>{self.t("video_note")}</figcaption>
</figure>
</div>
</section>
"""

    def problem(self):
        cards = "".join(
            f'<li class="glass card reveal">{icon(name, "ic ic-round")}<h3>{title}</h3><p>{text}</p></li>'
            for name, (title, text) in zip(("hand", "screen", "pulse"), self.t("pain")))
        return f"""<section class="section" id="why">
<div class="wrap">
<h2 class="reveal">{self.t("pain_title")}</h2>
<ul class="grid g3">{cards}</ul>
<p class="punch reveal">{self.t("pain_end")}</p>
</div>
</section>
"""

    def steps(self):
        cards = "".join(
            f'<li class="glass card step reveal"><span class="num" aria-hidden="true">{n}</span><h3>{title}</h3><p>{text}</p></li>'
            for n, (title, text) in enumerate(self.t("steps"), 1))
        checks = "".join(f"<li>{icon('check')}{c}</li>" for c in self.t("checks"))
        return f"""<section class="section" id="start">
<div class="wrap">
<h2 class="reveal">{self.t("steps_title")}</h2>
<ol class="grid g3 steps">{cards}</ol>
<ul class="chips reveal">{checks}</ul>
<p class="aside reveal">{self.t("steps_linux")} {self.ext(LINUX_HELP[self.i], self.t("steps_linux_link"))} ·
{self.ext(GUIDE[self.i], self.t("guide_link"))}</p>
</div>
</section>
"""

    def gestures(self):
        cards = "".join(
            f'<li class="glass card gesture reveal">{demo_svg(kind, f"{name} — {does}")}'
            f'<h3>{name} <span class="does">{icon("arrow")}{does}</span></h3><p>{text}</p></li>'
            for kind, (name, does, text) in zip(("cursor", "click", "scroll", "drag"), self.t("gestures")))
        more = "".join(f"<li>{m}</li>" for m in self.t("g_more"))
        return f"""<section class="section" id="gestures">
<div class="wrap">
<h2 class="reveal">{self.t("g_title")}</h2>
<p class="sub reveal">{self.t("g_sub")}</p>
<ul class="grid g4">{cards}</ul>
<ul class="chips plain reveal">{more}</ul>
<p class="aside reveal">{self.ext(GUIDE[self.i], self.t("g_all") + icon("arrow"), "more")}</p>
</div>
</section>
"""

    def features(self):
        shots = (f"img/{self.lang}/widgets.webp", f"img/{self.lang}/notebook.webp", None,
                 f"img/{self.lang}/twohands.webp", f"img/{self.lang}/access.webp")
        rows = ""
        for n, ((title, text, points, alt), shot) in enumerate(zip(self.t("features"), shots)):
            picture = (f'<div class="shot{" tall" if n >= 3 else ""}">{self.img(shot, alt)}</div>' if shot
                       else f'<div class="shot drawn">{face_svg(self.t("face_alt"))}</div>')
            note = (f'<p class="fine">{self.t("f_face_note")}</p>' if n == 2
                    else f'<p class="fine">{self.t("f_access")}</p>' if n == 4 else "")
            items = "".join(f"<li>{icon('check')}<span>{p}</span></li>" for p in points)
            rows += (f'<article class="feature reveal{" flip" if n % 2 else ""}"><div class="feature-text"><h3>{title}</h3>'
                     f'<p>{text}</p><ul class="ticks">{items}</ul>{note}</div>{picture}</article>')
        extras = "".join(
            f'<li class="glass card small reveal">{icon(name, "ic ic-round")}<h3>{title}</h3><p>{text}</p></li>'
            for name, (title, text) in zip(("palette", "sliders", "bolt", "globe"), self.t("extras")))
        designs = "".join(
            f'<figure class="reveal">{self.img(f"img/{self.lang}/{name}.webp", self.t("designs_alt", label))}'
            f'<figcaption>{label}</figcaption></figure>'
            for name, label in zip(("glass", "nature", "classic"), self.t("designs")))
        return f"""<section class="section" id="features">
<div class="wrap">
<h2 class="reveal">{self.t("f_title")}</h2>
<p class="sub reveal">{self.t("f_sub")}</p>
{rows}
<ul class="grid g4 extras">{extras}</ul>
<div class="designs">{designs}</div>
</div>
</section>
"""

    def numbers(self):
        stats = "".join(f'<li class="glass stat reveal"><b>{value}</b><span>{text}</span></li>'
                        for value, text in self.t("stats"))
        how = "".join(f"<li>{line}</li>" for line in self.t("how"))
        return f"""<section class="section" id="numbers">
<div class="wrap">
<h2 class="reveal">{self.t("p_title")}</h2>
<p class="sub reveal">{self.t("p_sub")}</p>
<ul class="grid g4 stats">{stats}</ul>
<div class="glass how reveal">
<h3>{self.t("how_title")}</h3>
<ol>{how}</ol>
</div>
<p class="fine center reveal">{self.t("p_note")} {self.ext(KPI, self.t("p_kpi"))}</p>
</div>
</section>
"""

    def privacy(self):
        items = "".join(
            f'<li>{icon(name, "ic ic-round")}<div><h3>{title}</h3><p>{text}</p></div></li>'
            for name, (title, text) in zip(("wifi_off", "user_off", "code", "folder"), self.t("priv")))
        return f"""<section class="section" id="privacy">
<div class="wrap">
<div class="glass privacy reveal">
<div class="privacy-head">{icon("shield", "ic ic-hero")}
<h2>{self.t("priv_title")}</h2>
<p>{self.t("priv_sub")}</p></div>
<ul class="privacy-list">{items}</ul>
</div>
</div>
</section>
"""

    def download(self):
        return f"""<section class="section" id="download">
<div class="wrap">
<h2 class="reveal">{self.t("dl_title")}</h2>
<p class="sub reveal">{self.t("dl_sub")}</p>
<div class="grid g2 platforms">
<div class="glass card platform reveal">
<h3>{icon("windows")}{self.t("dl_win_name")}</h3>
<p>{self.t("dl_win_text")}</p>
<a class="btn btn-primary" href="{WIN_URL}">{icon("download")}<span><b>{self.t("btn_win")}</b><small>{self.t("btn_win_note")}</small></span></a>
</div>
<div class="glass card platform reveal">
<h3>{icon("linux")}{self.t("dl_linux_name")}</h3>
<p>{self.t("dl_linux_text")}</p>
<a class="btn btn-glass" href="{LINUX_URL}">{icon("download")}<span><b>{self.t("btn_linux")}</b><small>{self.t("btn_linux_note")}</small></span></a>
<p class="fine">{self.t("dl_linux_new")}</p>
</div>
</div>
<p class="aside reveal">{self.t("dl_version", VERSION)} · {self.ext(RELEASES, self.t("dl_all"))} ·
{self.ext(REPO, self.t("dl_source"))} · {self.ext(ISSUES, self.t("dl_report"))}</p>
</div>
</section>
"""

    def support(self):
        """Free and Pro. Pro is only announced; the donation buttons appear when SUPPORT has links."""
        if not PRO:
            return ""
        points = "".join(f"<li>{icon('check')}<span>{p}</span></li>" for p in self.t("pro_free_points"))
        news = (self.ext(TELEGRAM, self.t("pro_news") + icon("arrow"), "more") if TELEGRAM else "")
        gifts = "".join(self.ext(url, f"<span><b>{name}</b></span>", "btn btn-glass") for name, url in SUPPORT.items() if url)
        support = (f'<div class="glass support reveal"><div><h3>{self.t("pro_support")}</h3><p>{self.t("pro_support_text")}</p></div>'
                   f'<div class="cta-row">{gifts}</div></div>' if gifts else "")
        return f"""<section class="section" id="pro">
<div class="wrap">
<h2 class="reveal">{self.t("pro_title")}</h2>
<p class="sub reveal">{self.t("pro_sub")}</p>
<div class="grid g2 plans">
<div class="glass card plan reveal">
<h3>{self.t("pro_free_name")}</h3>
<p>{self.t("pro_free_text")}</p>
<ul class="ticks">{points}</ul>
<a class="btn btn-primary" href="#download">{icon("download")}<span><b>{self.t("nav_download")}</b></span></a>
</div>
<div class="glass card plan soon reveal">
<h3>{self.t("pro_name")} <span class="badge">{self.t("pro_badge")}</span></h3>
<p>{self.t("pro_text")}</p>
{news}
</div>
</div>
{support}
</div>
</section>
"""

    def faq(self):
        free = self.t("faq_free")
        items = (((free[0], free[1] + (self.t("faq_pro") if PRO else "")),) if FREE else ()) + self.t("faq")
        rows = "".join(f'<details class="glass qa"><summary><span>{q}</span>{icon("plus")}</summary><p>{a}</p></details>'
                       for q, a in items)
        return f"""<section class="section" id="faq">
<div class="wrap narrow">
<h2 class="reveal">{self.t("faq_title")}</h2>
<div class="faq reveal">{rows}</div>
</div>
</section>
"""

    def gallery(self):
        if self.lang != "ru":           # the carousel and the poster are in Russian
            return ""
        slides = "".join(f'<li>{self.img(f"img/carousel/{n:02d}.webp", alt)}</li>'
                         for n, alt in enumerate(T["gal_alt"], 1))
        return f"""<section class="section" id="gallery">
<div class="wrap">
<h2 class="reveal">{self.t("gal_title")}</h2>
</div>
<ul class="strip reveal" tabindex="0" aria-label="{self.t("gal_title")}">{slides}</ul>
</section>
"""

    def call(self):
        return f"""<section class="section" id="try">
<div class="wrap">
<div class="glass final reveal">
<img src="{self.asset("icon.png")}" width="72" height="72" alt="" loading="lazy">
<h2>{self.t("cta_title_free" if FREE else "cta_title")}</h2>
<p>{self.t("cta_sub")}</p>
{self.downloads()}
</div>
</div>
</section>
"""

    def footer(self):
        return f"""<footer class="foot">
<div class="wrap foot-in">
<div class="foot-brand"><a class="brand" href="#top"><img src="{self.asset("icon.png")}" width="30" height="30" alt="" loading="lazy"><span>AirMouse</span></a>
<p>{self.t("foot_tag")}</p></div>
<nav aria-label="{self.t("foot_product")}"><h3>{self.t("foot_product")}</h3>
<a href="{WIN_URL}">{self.t("btn_win")}</a><a href="{LINUX_URL}">{self.t("btn_linux")}</a>
{self.ext(RELEASES, self.t("foot_releases"))}{self.ext(REPO, self.t("foot_github"))}</nav>
<nav aria-label="{self.t("foot_help")}"><h3>{self.t("foot_help")}</h3>
{self.ext(GUIDE[self.i], self.t("foot_guide"))}{self.ext(VIDEO_GUIDE, self.t("foot_video_guide"))}
<a href="#faq">{self.t("faq_title")}</a>{self.ext(ISSUES, self.t("foot_issues"))}
{self.ext(TELEGRAM, self.t("foot_telegram")) if TELEGRAM else ""}</nav>
</div>
<div class="wrap foot-end"><span>© 2026 AirMouse</span><a href="#top">{self.t("foot_top")} ↑</a></div>
</footer>
"""

    def render(self):
        body = "".join((self.hero(), self.problem(), self.steps(), self.gestures(), self.features(), self.numbers(),
                        self.privacy(), self.download(), self.support(), self.faq(), self.gallery(), self.call()))
        return (f'{self.head()}<body data-lang="{self.lang}">\n{self.header()}<main id="main">\n{body}</main>\n'
                f'{self.footer()}<script src="{self.root}app.js" defer></script>\n</body>\n</html>\n')


# -- pictures and video for the web -----------------------------------------------------------------
def build_assets():
    import cv2
    import imageio_ffmpeg

    promo, docs = ROOT / "promo", ROOT / "docs"
    for folder in ("video", "img/ru", "img/en", "img/carousel"):
        (ASSETS / folder).mkdir(parents=True, exist_ok=True)

    def webp(picture, path, quality=86):
        picture.convert("RGB").save(ASSETS / path, "WEBP", quality=quality, method=6)

    def frame(video, seconds):
        cap = cv2.VideoCapture(str(video))
        cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, picture = cap.read()
        cap.release()
        if not ok:
            raise SystemExit(f"cannot read {video}")
        return Image.fromarray(cv2.cvtColor(picture, cv2.COLOR_BGR2RGB))

    for lang, name in (("ru", "AirMouse_ad.mp4"), ("en", "AirMouse_ad_en.mp4")):
        src = promo / name
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(src),
               "-vf", "scale=1280:720:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-crf", "24",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
               str(ASSETS / f"video/airmouse-ad-{lang}.mp4")]
        if subprocess.run(cmd).returncode:
            raise SystemExit("ffmpeg failed")
        reveal = frame(src, 12.500)                                  # the name and the promise
        reveal.resize((1280, 720), Image.LANCZOS).save(ASSETS / f"img/film-{lang}.jpg", quality=86, optimize=True)
        reveal.resize((1200, 675), Image.LANCZOS).crop((0, 22, 1200, 652)).save(
            ASSETS / f"img/og-{lang}.jpg", quality=88, optimize=True)
        webp(frame(src, 41.500).crop((92, 196, 968, 884)), f"img/{lang}/notebook.webp")   # the notebook itself

    for lang, folder in (("ru", docs), ("en", docs / "en")):
        for name, out in (("widgets", "widgets"), ("twohands", "twohands"), ("accessibility", "access"),
                          ("glass", "glass"), ("nature", "nature"), ("classic", "classic")):
            webp(Image.open(folder / f"screenshot_{name}.png"), f"img/{lang}/{out}.webp")

    for n in range(1, 9):
        webp(Image.open(promo / f"carousel/AirMouse_{n:02d}.jpg").resize((720, 900), Image.LANCZOS),
             f"img/carousel/{n:02d}.webp", 84)

    ico = Image.open(ROOT / "assets/airmouse.ico")
    ico.size = max(ico.info.get("sizes", {ico.size}))                # the largest picture in the .ico
    large = ico.convert("RGBA")
    large.resize((192, 192), Image.LANCZOS).save(ASSETS / "icon-192.png")
    large.resize((144, 144), Image.LANCZOS).save(ASSETS / "icon.png")
    (ASSETS / "favicon.ico").write_bytes((ROOT / "assets/airmouse.ico").read_bytes())


NOT_FOUND = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AirMouse — страница не найдена</title>
<meta name="robots" content="noindex">
<meta name="theme-color" content="#06101f">
<link rel="icon" href="/assets/favicon.ico" sizes="any">
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<div class="backdrop" aria-hidden="true"><i class="orb o1"></i><i class="orb o2"></i><i class="orb o3"></i></div>
<main class="hero">
<div class="wrap hero-in">
<a class="brand" href="/"><img src="/assets/icon.png" width="34" height="34" alt=""><span>AirMouse</span></a>
<h1>404</h1>
<p class="lead">Такой страницы нет.<br><span lang="en">This page does not exist.</span></p>
<div class="cta-row">
<a class="btn btn-primary" href="/"><span><b>На главную</b></span></a>
<a class="btn btn-glass" href="/en/" lang="en"><span><b>Home page</b></span></a>
</div>
</div>
</main>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--assets", action="store_true", help="rebuild site/assets from promo/ and docs/")
    args = parser.parse_args()
    if args.assets:
        build_assets()
    for lang in LANGS:
        out = SITE / ("index.html" if lang == "ru" else "en/index.html")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(Page(lang).render(), encoding="utf-8", newline="\n")
        print(out.relative_to(ROOT))
    (SITE / "404.html").write_text(NOT_FOUND, encoding="utf-8", newline="\n")
    if SITE_URL:
        (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", newline="\n")
        (SITE / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"<url><loc>{SITE_URL}/</loc></url>\n<url><loc>{SITE_URL}/en/</loc></url>\n</urlset>\n", newline="\n")


if __name__ == "__main__":
    main()
