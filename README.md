# 📊 公開資訊 CSV 資料瀏覽器（Gradio + PWA + RWD）

輸入 CSV 連結後，可搜尋、繪圖、檢視欄位統計並下載結果。
預設資料來源為公開資訊觀測站開放資料（`t187ap46_L_1.csv`），也可貼上其他 CSV 連結。

## 功能

- 載入遠端 CSV（`utf-8-sig`，支援繁體中文），可選擇是否移除空值列
- 統計卡片：資料筆數、欄位數、數值欄位數、已移除空值列
- 🔎 資料表：關鍵字搜尋（可指定欄位）、下載篩選後的 CSV
- 📈 圖表：Top N 長條圖、直方圖、散佈圖、箱形圖
- 🧮 欄位統計：欄位型態、缺值數、不重複值、`describe`
- **PWA**：可安裝到手機／桌面，獨立視窗開啟，有離線提示頁
- **RWD**：手機、平板、桌面自動調整版面

## 專案結構

```
.
├── app.py             # Gradio 介面 + FastAPI 掛載
├── pwa.py             # manifest、Service Worker、離線頁、圖示（執行時產生）
├── requirements.txt
└── README.md
```

不需要任何圖檔：PWA 圖示由 `pwa.py` 在執行時產生。

## 本機執行

```bash
pip install -r requirements.txt
python app.py
```

開啟 http://localhost:7860（`localhost` 被瀏覽器視為安全來源，可測試 PWA）。

## 上傳到 GitHub

```bash
git init
git add app.py pwa.py requirements.txt README.md
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<你的帳號>/<repo 名稱>.git
git push -u origin main
```

## 部署到 Render

1. 登入 [Render](https://render.com)，選 **New → Web Service**，連結 GitHub repo。
2. 設定：

   | 項目 | 值 |
   |---|---|
   | Language / Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `python app.py` |
   | Health Check Path（選填） | `/healthz` |

3. （建議）在 **Environment** 新增 `PYTHON_VERSION`，例如 `3.11.9`。
4. 部署完成後會得到 `https://xxx.onrender.com`。Render 提供 HTTPS，PWA 才能安裝。

`app.py` 會讀取 Render 的 `PORT` 環境變數，並綁定 `0.0.0.0`。

## 安裝成 App

| 裝置 | 方式 |
|---|---|
| Android Chrome | 點畫面右下角「📲 安裝 App」，或瀏覽器選單 → 安裝應用程式 |
| 桌面 Chrome / Edge | 網址列右側的安裝圖示 |
| iPhone / iPad Safari | 分享 → 加入主畫面（iOS 不會出現安裝按鈕） |

## PWA 運作說明

- 此 App 需要伺服器才能載入資料與繪圖。**離線時只會顯示離線提示頁**，不能離線使用資料功能。
- Service Worker 只快取靜態資源（`/assets`、`/static`、`/_app`、`/icons`）與離線頁；Gradio 的 API、佇列、檔案下載一律走網路。
- 想強制所有使用者更新快取：修改 `pwa.py` 的 `SW_VERSION`。
- Gradio 本身的 HTML 帶有 `/manifest.json` 連結，`pwa.py` 已讓該路徑也回傳我們的 manifest。

## 已測試與未測試

已在本機實測（Gradio 5.50.0、headless Chromium）：
- `/manifest.json`、`/manifest.webmanifest`、`/sw.js`、`/offline.html`、圖示、`/healthz` 皆回應 200
- Service Worker 成功註冊
- 載入本機範例 CSV 後，統計卡片與圖表正常顯示
- 390px（手機）與 1280px（桌面）寬度皆無橫向捲軸

尚未測試：
- 實際部署到 Render
- 實際連到公開資訊觀測站網址（測試環境無法連外）
- 瀏覽器真正跳出安裝提示、離線頁顯示、iOS 加入主畫面

## 注意事項

- 預設不驗證 SSL 憑證（`verify=False`，沿用原本寫法），介面上可勾選「驗證 SSL 憑證」。
- 請固定使用 Gradio 5.x（`requirements.txt` 已限制 `<6.0`），因為 `theme`、`css`、`head` 傳入位置在 6.x 可能不同，未驗證。
- Render 免費方案可能在閒置後休眠，休眠規則依 Render 目前方案為準，未查證。
