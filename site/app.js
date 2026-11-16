/* AirMouse website: the menu, the language, the right download button, the film and the moving gesture pictures.
   The page works without this file; it only adds comfort. */
(function () {
  "use strict";

  var doc = document, root = doc.documentElement, body = doc.body;
  var lang = body.getAttribute("data-lang") || "ru";
  var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var each = function (selector, fn, scope) { Array.prototype.forEach.call((scope || doc).querySelectorAll(selector), fn); };

  function stored(key, value) {
    try {
      if (value === undefined) return window.localStorage.getItem(key);
      window.localStorage.setItem(key, value);
    } catch (e) { /* private window: no storage, nothing to remember */ }
    return null;
  }

  // -- header: glass after the first scroll, the menu on narrow screens ---------------------------
  var top = doc.querySelector(".top"), nav = doc.getElementById("nav"), burger = doc.querySelector(".burger");
  function stick() { top.classList.toggle("stuck", window.scrollY > 8); }
  window.addEventListener("scroll", stick, { passive: true });
  stick();
  function menu(open) {
    nav.classList.toggle("open", open);
    burger.setAttribute("aria-expanded", String(open));
  }
  burger.addEventListener("click", function () { menu(!nav.classList.contains("open")); });
  nav.addEventListener("click", function (e) { if (e.target.tagName === "A") menu(false); });
  doc.addEventListener("keydown", function (e) { if (e.key === "Escape") menu(false); });

  // -- language: remember the choice, and offer the other page once to those who read the other language --
  each(".lang a", function (a) {
    a.addEventListener("click", function () { stored("airmouse_lang", a.getAttribute("data-lang")); });
  });
  var speaksRussian = /^(ru|be|kk|ky|tg|uz)\b/i.test(navigator.language || "");
  if (!stored("airmouse_lang") && speaksRussian !== (lang === "ru")) {
    var other = doc.querySelector('.lang a:not(.on)');
    var bar = doc.createElement("div");
    bar.className = "other-lang";
    var link = doc.createElement("a");
    link.href = other.getAttribute("href");
    link.textContent = lang === "ru" ? "This page is available in English →" : "Эта страница есть на русском →";
    link.addEventListener("click", function () { stored("airmouse_lang", other.getAttribute("data-lang")); });
    var close = doc.createElement("button");
    close.type = "button";
    close.setAttribute("aria-label", lang === "ru" ? "Close" : "Закрыть");
    close.textContent = "×";
    close.addEventListener("click", function () { stored("airmouse_lang", lang); bar.remove(); });
    bar.appendChild(link);
    bar.appendChild(close);
    body.insertBefore(bar, top);
  }

  // -- downloads: Linux first for Linux, a hint for phones ---------------------------------------
  var ua = navigator.userAgent || "";
  var phone = /Android|iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
  if (!phone && /Linux|X11/i.test(navigator.platform || ua)) {
    each("[data-downloads]", function (row) {
      var win = row.querySelector('[data-os="win"]'), linux = row.querySelector('[data-os="linux"]');
      win.classList.replace("btn-primary", "btn-glass");
      linux.classList.replace("btn-glass", "btn-primary");
      row.insertBefore(linux, win);
    });
  }
  if (phone) each(".phone-hint", function (hint) { hint.hidden = false; });
  each("[data-copy]", function (button) {
    var label = button.textContent;
    button.addEventListener("click", function () {
      var url = location.href.split("#")[0];
      var done = function () {
        button.textContent = button.getAttribute("data-done");
        setTimeout(function () { button.textContent = label; }, 2500);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done, function () { window.prompt(label, url); });
      } else {
        window.prompt(label, url);
      }
    });
  });

  // -- the film: one big button, then the ordinary player ----------------------------------------
  each(".film", function (film) {
    var video = film.querySelector("video"), play = film.querySelector(".film-play");
    video.controls = false;                      // the player's own buttons come with the first play
    play.addEventListener("click", function () {
      film.classList.add("playing");
      video.controls = true;
      var started = video.play();
      if (started && started.catch) started.catch(function () { /* the controls are there */ });
    });
    video.addEventListener("play", function () { film.classList.add("playing"); video.controls = true; });
  });

  // -- sections arrive as they scroll into view ---------------------------------------------------
  if ("IntersectionObserver" in window && !calm) {
    var seen = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { entry.target.classList.add("in"); seen.unobserve(entry.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    each(".reveal", function (el) { seen.observe(el); });
  } else {
    each(".reveal", function (el) { el.classList.add("in"); });
  }

  // -- the four gestures, moving -------------------------------------------------------------------
  // The same hand as airmouse/bench.py and tools/build_site.py: 21 points, palm length 100.
  function hand(pinch, pose) {
    var ox = 112, oy = 96, pts = new Array(21);
    var mcp = { 5: [ox - 50, oy + 5], 9: [ox, oy], 13: [ox + 50, oy + 5], 17: [ox + 95, oy + 15] };
    pts[0] = [ox, oy + 100];
    Object.keys(mcp).forEach(function (key) {
      var i = +key, folded = pose === "two" && (i === 13 || i === 17);
      (folded ? [0, -30, -15, 10] : [0, -40, -65, -90]).forEach(function (off, k) {
        pts[i + k] = [mcp[key][0], mcp[key][1] + off];
      });
    });
    pts[1] = [ox - 60, oy + 80]; pts[2] = [ox - 85, oy + 55]; pts[3] = [ox - 100, oy + 30];
    var tip = [pts[8][0], pts[8][1] + 8], away = [ox - 110, oy + 5];
    pts[4] = [away[0] + (tip[0] - away[0]) * pinch, away[1] + (tip[1] - away[1]) * pinch];
    return pts;
  }
  var LINES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
               [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];
  var ease = function (x) { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  var between = function (t, a, b) { return ease((t - a) / (b - a)); };

  function Demo(svg) {
    this.kind = svg.getAttribute("data-gesture");
    this.at = svg.querySelector(".hand-at");
    this.bones = svg.querySelectorAll(".bones line");
    this.joints = svg.querySelectorAll(".joints circle");
    this.palm = svg.querySelector(".palm");
    this.cursor = svg.querySelector(".cursor");
    this.svg = svg;
    this.pose = this.kind === "scroll" ? "two" : "open";
  }
  Demo.prototype.shape = function (pinch) {
    var pts = hand(pinch, this.pose), i;
    for (i = 0; i < LINES.length; i++) {
      var a = pts[LINES[i][0]], b = pts[LINES[i][1]], line = this.bones[i];
      line.setAttribute("x1", a[0]); line.setAttribute("y1", a[1]);
      line.setAttribute("x2", b[0]); line.setAttribute("y2", b[1]);
    }
    for (i = 0; i < 21; i++) { this.joints[i].setAttribute("cx", pts[i][0]); this.joints[i].setAttribute("cy", pts[i][1]); }
  };
  Demo.prototype.move = function (dx, dy) {
    this.at.setAttribute("transform", "translate(" + (6 + dx).toFixed(2) + " " + (26 + dy).toFixed(2) + ") scale(.76)");
  };
  Demo.prototype.point = function (x, y) {
    this.cursor.setAttribute("transform", "translate(" + x.toFixed(2) + " " + y.toFixed(2) + ")");
  };
  Demo.prototype.frame = function (now) {
    var svg = this.svg, t, p, x, y;
    if (this.kind === "cursor") {
      t = (now % 5) / 5 * Math.PI * 2;
      x = Math.sin(t); y = Math.sin(2 * t);
      this.move(16 * x, 9 * y);
      x = 59 + 36 * x; y = 38 + 15 * y;
      this.point(x, y);
      each(".tiles rect", function (tile) {
        var tx = +tile.getAttribute("x"), ty = +tile.getAttribute("y");
        tile.classList.toggle("on", x >= tx && x <= tx + 26 && y >= ty && y <= ty + 20);
      }, svg);
    } else if (this.kind === "click") {
      t = now % 2.6;
      p = between(t, 0.3, 1.0) - between(t, 1.35, 1.7);
      this.shape(p);
      svg.querySelector(".ring").style.strokeDashoffset = String(100 - 100 * p);
      svg.querySelector(".button").classList.toggle("on", t > 0.98 && t < 1.45);
    } else if (this.kind === "scroll") {
      t = Math.sin((now % 4) / 4 * Math.PI * 2);
      this.move(0, -13 * t);
      svg.querySelector(".rows").setAttribute("transform", "translate(0 " + (-32 - 30 * t).toFixed(2) + ")");
    } else {
      t = now % 4.4;
      p = between(t, 0.2, 0.7) - between(t, 2.3, 2.7);
      x = between(t, 0.9, 2.1) - between(t, 3.0, 4.0);
      this.shape(p);
      this.move(14 * x, 0);
      this.point(29 + 60 * x, 57);
      var tile = svg.querySelector(".tile");
      tile.setAttribute("x", (12 + 60 * (t < 3.5 ? between(t, 0.9, 2.1) : 0)).toFixed(2));
      tile.style.opacity = String(1 - between(t, 3.0, 3.4) + between(t, 3.6, 4.0));
    }
  };

  if (!calm && "IntersectionObserver" in window && window.requestAnimationFrame) {
    var live = [], running = false;
    var tick = function (ms) {
      for (var i = 0; i < live.length; i++) live[i].frame(ms / 1000);
      if (live.length) window.requestAnimationFrame(tick); else running = false;
    };
    var watch = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var demo = entry.target.__demo, at = live.indexOf(demo);
        if (entry.isIntersecting && at < 0) live.push(demo);
        if (!entry.isIntersecting && at >= 0) live.splice(at, 1);
      });
      if (live.length && !running) { running = true; window.requestAnimationFrame(tick); }
    }, { threshold: 0.2 });
    each(".demo", function (svg) { svg.__demo = new Demo(svg); watch.observe(svg); });
  }
})();
