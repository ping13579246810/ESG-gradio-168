"""PWA 模組：manifest、Service Worker、離線頁、圖示（執行時產生，不需圖檔）。"""
import json
import struct
import zlib
from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

APP_NAME = "公開資訊 CSV 資料瀏覽器"
SHORT_NAME = "MOPS CSV"
THEME_COLOR = "#0f766e"
BG_COLOR = "#f8fafc"
SW_VERSION = "v1"  # 更新前端快取策略時，改這個字串即可強制更新

MANIFEST = {
    "name": APP_NAME,
    "short_name": SHORT_NAME,
    "description": "輸入 CSV 連結，搜尋、統計、繪圖與下載。",
    "id": "/",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "orientation": "any",
    "lang": "zh-TW",
    "theme_color": THEME_COLOR,
    "background_color": BG_COLOR,
    "icons": [
        {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}

# 放進 <head> 的標籤與註冊腳本（含「安裝 App」按鈕）
PWA_HEAD = f"""
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="{THEME_COLOR}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{SHORT_NAME}">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<script>
// Gradio 會在頁面載入後才注入 head，load 事件可能已經發生，所以要先檢查 readyState
function registerSW() {{
  navigator.serviceWorker.register("/sw.js", {{ scope: "/" }}).catch(console.warn);
}}
if ("serviceWorker" in navigator) {{
  if (document.readyState === "complete") registerSW();
  else window.addEventListener("load", registerSW);
}}
(function () {{
  var deferred = null;
  function removeBtn() {{
    var b = document.getElementById("pwa-install");
    if (b) b.remove();
  }}
  window.addEventListener("beforeinstallprompt", function (e) {{
    e.preventDefault();
    deferred = e;
    if (document.getElementById("pwa-install")) return;
    var b = document.createElement("button");
    b.id = "pwa-install";
    b.textContent = "📲 安裝 App";
    b.onclick = function () {{
      if (!deferred) return;
      deferred.prompt();
      deferred.userChoice.then(function () {{ deferred = null; removeBtn(); }});
    }};
    document.body.appendChild(b);
  }});
  window.addEventListener("appinstalled", removeBtn);
}})();
</script>
"""

SERVICE_WORKER = f"""
const VERSION = "{SW_VERSION}";
const STATIC_CACHE = "mops-static-" + VERSION;
const PRECACHE = ["/offline.html", "/icons/icon-192.png", "/icons/icon-512.png", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {{
  event.waitUntil(
    caches.open(STATIC_CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
}});

self.addEventListener("activate", (event) => {{
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k.startsWith("mops-") && k !== STATIC_CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
}});

self.addEventListener("fetch", (event) => {{
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Gradio 的 API / 佇列 / 檔案下載一律走網路，不快取
  if (url.pathname.startsWith("/gradio_api/") || url.pathname.startsWith("/queue") ||
      url.pathname.startsWith("/file") || url.pathname.startsWith("/upload") ||
      url.pathname.startsWith("/run") || url.pathname === "/config") return;

  // 頁面導覽：網路優先，離線時顯示離線頁
  if (req.mode === "navigate") {{
    event.respondWith(fetch(req).catch(() => caches.match("/offline.html")));
    return;
  }}

  // 靜態資源：先用快取、背景更新 (stale-while-revalidate)
  if (/^\\/(assets|static|_app|icons)\\//.test(url.pathname) || url.pathname === "/manifest.webmanifest") {{
    event.respondWith(
      caches.open(STATIC_CACHE).then(async (cache) => {{
        const hit = await cache.match(req);
        const net = fetch(req)
          .then((res) => {{ if (res && res.ok) cache.put(req, res.clone()); return res; }})
          .catch(() => hit);
        return hit || net;
      }})
    );
  }}
}});
"""

OFFLINE_HTML = f"""<!doctype html>
<html lang="zh-TW"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="{THEME_COLOR}">
<title>目前離線</title>
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;
       font-family:"Noto Sans TC",system-ui,sans-serif;background:{BG_COLOR};color:#0f172a}}
  .box{{max-width:420px;text-align:center;background:#fff;border-radius:20px;padding:36px 28px;
       box-shadow:0 12px 30px rgba(15,23,42,.12)}}
  .emoji{{font-size:3rem}}
  h1{{font-size:1.4rem;margin:12px 0 8px}}
  p{{margin:0 0 20px;opacity:.7;line-height:1.6}}
  button{{border:0;border-radius:12px;padding:12px 22px;font-size:1rem;font-weight:600;
         color:#fff;background:linear-gradient(120deg,#0f766e,#2563eb);cursor:pointer}}
</style></head>
<body><div class="box">
  <div class="emoji">📡</div>
  <h1>目前沒有網路連線</h1>
  <p>載入資料與繪圖需要連線到伺服器。請確認網路後再試一次。</p>
  <button onclick="location.reload()">重新整理</button>
</div></body></html>
"""


# ---------- 純 Python 產生 PNG 圖示（不需 Pillow / 圖檔） ----------
def _chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


@lru_cache(maxsize=8)
def make_icon(size: int) -> bytes:
    c1, c2 = (15, 118, 110), (37, 99, 235)  # 青綠 → 藍，對應標題漸層
    n = 2 * (size - 1) + 1
    lut = [
        bytes(int(c1[k] + (c2[k] - c1[k]) * d / (n - 1)) for k in range(3)) for d in range(n)
    ]

    # 三根長條圖（全部落在中央安全區，maskable 也不會被裁到）
    bw, gap = int(size * 0.12), int(size * 0.06)
    x0 = (size - (3 * bw + 2 * gap)) // 2
    base = int(size * 0.68)
    heights = [0.20, 0.32, 0.44]
    bars = [(x0 + i * (bw + gap), x0 + i * (bw + gap) + bw, base - int(size * h))
            for i, h in enumerate(heights)]

    raw = bytearray()
    white = b"\xff\xff\xff"
    for y in range(size):
        row = bytearray(b"".join(lut[x + y] for x in range(size)))
        if y < base:
            for a, b, top in bars:
                if y >= top:
                    row[3 * a:3 * b] = white * (b - a)
        raw += b"\x00" + row

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b""))


# ---------- 路由 ----------
def register_pwa(app: FastAPI) -> None:
    """必須在 mount_gradio_app 之前呼叫，路由才會優先於 Gradio。"""

    # Gradio 的 HTML 本身就帶有 <link rel="manifest" href="/manifest.json">，
    # 未啟用其內建 PWA 時會回 404，所以兩個路徑都回傳我們自己的 manifest。
    @app.get("/manifest.json", include_in_schema=False)
    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return Response(json.dumps(MANIFEST, ensure_ascii=False),
                        media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js", include_in_schema=False)
    def sw():
        return Response(SERVICE_WORKER, media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    @app.get("/offline.html", include_in_schema=False)
    def offline():
        return HTMLResponse(OFFLINE_HTML)

    @app.get("/icons/icon-192.png", include_in_schema=False)
    def icon192():
        return Response(make_icon(192), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/icons/icon-512.png", include_in_schema=False)
    def icon512():
        return Response(make_icon(512), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/apple-touch-icon.png", include_in_schema=False)
    def apple_icon():
        return Response(make_icon(192), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
