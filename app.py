# ============================================================
# 公開資訊 CSV 資料瀏覽器 — Gradio + PWA + RWD（可部署到 Render）
# 本機執行：python app.py   →   http://localhost:7860
# ============================================================
import io
import os
import re
import tempfile
import warnings

import gradio as gr
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import uvicorn
from fastapi import FastAPI

from pwa import APP_NAME, PWA_HEAD, register_pwa

warnings.filterwarnings("ignore")  # 隱藏 verify=False 的 SSL 警告

DEFAULT_URL = "https://mopsfin.twse.com.tw/opendata/t187ap46_L_1.csv"  # 換連結
ALL = "(全部欄位)"
MAX_ROWS = 1000
TEAL, INDIGO = "#14b8a6", "#4f46e5"
CHART_KINDS = ["Top N 長條圖", "直方圖", "散佈圖", "箱形圖"]


# ---------- 工具函式 ----------
def cards_html(total=None, ncols=None, nnum=None, dropped=None):
    def fmt(v):
        return "–" if v is None else f"{v:,}"

    items = [
        ("📄", "資料筆數", total),
        ("🧱", "欄位數", ncols),
        ("🔢", "數值欄位", nnum),
        ("🧹", "已移除空值列", dropped),
    ]
    body = "".join(
        f"<div class='card'><div class='card-label'>{ic} {lb}</div>"
        f"<div class='card-value'>{fmt(v)}</div></div>"
        for ic, lb, v in items
    )
    return f"<div class='cards'>{body}</div>"


def save_csv(df):
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", prefix="data_")
    df.to_csv(f.name, index=False, encoding="utf-8-sig")  # Excel 開啟不亂碼
    return f.name


def pick_defaults(df):
    num = list(df.select_dtypes(include="number").columns)
    cat = [c for c in df.columns if c not in num]
    skip = re.compile(r"代號|年度|日期|編號|code|id", re.I)
    value_cols = [c for c in num if not skip.search(str(c))] or num
    label = "公司名稱" if "公司名稱" in df.columns else (cat[0] if cat else df.columns[0])
    val = value_cols[0] if value_cols else None
    val2 = value_cols[1] if len(value_cols) > 1 else val
    return num, label, val, val2


def empty_fig(msg="請先載入資料"):
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(size=16, color="#94a3b8"))
    fig.update_layout(template="plotly_white", height=420,
                      xaxis_visible=False, yaxis_visible=False)
    return fig


# ---------- 載入資料 ----------
def load_data(url, verify_ssl, drop_na):
    try:
        resp = requests.get(url.strip(), verify=verify_ssl, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.BytesIO(resp.content), encoding="utf-8-sig")  # 繁體中文
    except Exception as e:
        return (None, f"❌ 載入失敗：{e}", cards_html(), pd.DataFrame(), None,
                gr.update(choices=[ALL], value=ALL),
                gr.update(choices=[]), gr.update(choices=[]), gr.update(choices=[]),
                pd.DataFrame(), pd.DataFrame())

    raw = len(df)
    if drop_na:
        df = df.dropna().reset_index(drop=True)
    dropped = raw - len(df)

    num, label, val, val2 = pick_defaults(df)
    cols = list(df.columns)

    info = pd.DataFrame({
        "欄位": cols,
        "型態": df.dtypes.astype(str).values,
        "缺值數": df.isna().sum().values,
        "不重複值": df.nunique().values,
    })
    desc = (df[num].describe().T.reset_index().rename(columns={"index": "欄位"})
            if num else pd.DataFrame())

    status = f"✅ 載入成功，共 {len(df):,} 筆資料、{df.shape[1]} 個欄位"
    return (
        df, status, cards_html(len(df), df.shape[1], len(num), dropped),
        df.head(MAX_ROWS), save_csv(df),
        gr.update(choices=[ALL] + cols, value=ALL),
        gr.update(choices=cols, value=label),
        gr.update(choices=num, value=val),
        gr.update(choices=num, value=val2),
        info, desc,
    )


# ---------- 搜尋 ----------
def search(df, kw, col):
    if df is None:
        return pd.DataFrame(), "⚠️ 請先按「載入資料」", None
    out = df
    kw = (kw or "").strip()
    if kw:
        target = out if col in (None, ALL) else out[[col]]
        mask = target.astype(str).apply(
            lambda s: s.str.contains(kw, case=False, na=False, regex=False)
        ).any(axis=1)
        out = out[mask]
    msg = f"🔎 符合 **{len(out):,}** 筆" + (
        f"（僅顯示前 {MAX_ROWS:,} 筆，完整結果請下載）" if len(out) > MAX_ROWS else ""
    )
    return out.head(MAX_ROWS), msg, save_csv(out)


# ---------- 圖表 ----------
def make_chart(df, kind, label, val, val2, topn):
    if df is None:
        return empty_fig()
    if not val:
        return empty_fig("此資料沒有數值欄位可繪圖")
    try:
        if kind == "Top N 長條圖":
            d = df[[label, val]].dropna().sort_values(val, ascending=False).head(int(topn))
            d[label] = d[label].astype(str)
            fig = px.bar(d.iloc[::-1], x=val, y=label, orientation="h",
                         color=val, color_continuous_scale="Teal")
            fig.update_yaxes(type="category")
            fig.update_layout(coloraxis_showscale=False, title=f"{val}　Top {len(d)}")
        elif kind == "直方圖":
            fig = px.histogram(df, x=val, nbins=40, color_discrete_sequence=[TEAL])
            fig.update_layout(title=f"{val} 分布")
        elif kind == "散佈圖":
            fig = px.scatter(df, x=val, y=val2, hover_name=label, opacity=0.7,
                             color_discrete_sequence=[INDIGO])
            fig.update_layout(title=f"{val} vs {val2}")
        else:
            fig = px.box(df, y=val, points="outliers", color_discrete_sequence=[TEAL])
            fig.update_layout(title=f"{val} 箱形圖")
        fig.update_layout(template="plotly_white", height=460, autosize=True,
                          margin=dict(l=10, r=10, t=60, b=10), title_font_size=15)
        return fig
    except Exception as e:
        return empty_fig(f"繪圖失敗：{e}")


# ---------- 樣式（含 RWD） ----------
CSS = """
footer {display: none !important;}
.gradio-container {
  max-width: 1240px !important; margin: auto;
  padding-left: max(12px, env(safe-area-inset-left)) !important;
  padding-right: max(12px, env(safe-area-inset-right)) !important;
}
.hero {background: linear-gradient(120deg,#0f766e 0%,#2563eb 100%);
       border-radius: 20px; color: #fff; margin-bottom: 8px;
       padding: clamp(18px, 4vw, 32px) clamp(18px, 5vw, 40px);
       box-shadow: 0 12px 30px rgba(37,99,235,.25);}
.hero h1 {margin: 0 0 6px; font-size: clamp(1.3rem, 4.5vw, 1.9rem); color:#fff;}
.hero p {margin: 0; opacity: .85; color:#fff; font-size: clamp(.85rem, 2.6vw, 1rem);}
.cards {display: grid; gap: 14px; margin: 8px 0 4px;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));}
.html-container {padding: 0 !important;}
/* 手機：避免寬表格把整個頁面撐出橫向捲軸 */
.gradio-container, .gradio-container main {max-width: 100% !important; min-width: 0 !important;}
.gradio-container .tabitem, .gradio-container .column, .gradio-container .row,
.gradio-container .block {min-width: 0; max-width: 100%;}
.gradio-container .tabitem {overflow-x: auto;}
.card {background: var(--background-fill-primary); border: 1px solid var(--border-color-primary);
       border-radius: 16px; padding: 16px 20px; box-shadow: 0 4px 14px rgba(0,0,0,.05);}
.card-label {font-size: .85rem; opacity: .7; margin-bottom: 6px;}
.card-value {font-size: clamp(1.5rem, 5vw, 2rem); font-weight: 700; color: #0f766e;}

#pwa-install {position: fixed; right: 16px; z-index: 9999;
  bottom: calc(16px + env(safe-area-inset-bottom));
  border: none; border-radius: 999px; padding: 12px 18px; cursor: pointer;
  background: #0f766e; color: #fff; font-weight: 600; font-size: .95rem;
  box-shadow: 0 8px 24px rgba(0,0,0,.28);}

@media (max-width: 640px) {
  .gradio-container {padding-left: 8px !important; padding-right: 8px !important;}
  .card {padding: 12px 14px;}
  .card-label {font-size: .78rem;}
  .gradio-container button {width: 100%;}
}
@media (display-mode: standalone) {
  .gradio-container {padding-top: max(8px, env(safe-area-inset-top)) !important;}
}
"""

theme = gr.themes.Soft(
    primary_hue="teal", secondary_hue="indigo", neutral_hue="slate",
    font=[gr.themes.GoogleFont("Noto Sans TC"), "sans-serif"],
)

# ---------- 介面 ----------
with gr.Blocks(title=APP_NAME, theme=theme, css=CSS, head=PWA_HEAD) as demo:
    state = gr.State(None)

    gr.HTML(
        "<div class='hero'><h1>📊 公開資訊 CSV 資料瀏覽器</h1>"
        "<p>輸入 CSV 連結 → 一鍵載入 → 搜尋、統計、繪圖、下載，全部在同一個頁面完成。</p></div>"
    )

    with gr.Row(equal_height=True):
        url_in = gr.Textbox(label="CSV 連結", value=DEFAULT_URL, lines=2, scale=5, min_width=240)
        load_btn = gr.Button("🚀 載入資料", variant="primary", scale=1, size="lg", min_width=140)
    with gr.Row():
        verify_cb = gr.Checkbox(label="驗證 SSL 憑證", value=False, min_width=160)
        dropna_cb = gr.Checkbox(label="移除含空值的列 (dropna)", value=True, min_width=160)

    status = gr.Markdown("尚未載入資料")
    cards = gr.HTML(cards_html())

    with gr.Tabs():
        # --- 資料表 ---
        with gr.Tab("🔎 資料表"):
            with gr.Row(equal_height=True):
                kw_in = gr.Textbox(label="關鍵字搜尋", placeholder="例如：台積電、2330 …",
                                   scale=3, min_width=200)
                col_in = gr.Dropdown(label="搜尋欄位", choices=[ALL], value=ALL,
                                     scale=2, min_width=200)
                search_btn = gr.Button("搜尋", variant="primary", scale=1, min_width=120)
            result_msg = gr.Markdown()
            table = gr.Dataframe(label="資料預覽", interactive=False, wrap=True)
            export_file = gr.File(label="⬇️ 下載目前結果 (CSV)")

        # --- 圖表 ---
        with gr.Tab("📈 圖表"):
            kind_in = gr.Radio(CHART_KINDS, value=CHART_KINDS[0], label="圖表類型")
            with gr.Row():
                label_in = gr.Dropdown(label="分類 / 名稱欄位", choices=[], min_width=200)
                val_in = gr.Dropdown(label="數值欄位 (X / 主要)", choices=[], min_width=200)
                val2_in = gr.Dropdown(label="第二數值欄位 (散佈圖 Y)", choices=[], min_width=200)
                topn_in = gr.Slider(5, 50, value=15, step=1, label="Top N", min_width=200)
            chart_btn = gr.Button("繪製圖表", variant="primary")
            plot = gr.Plot(label="圖表")

        # --- 欄位統計 ---
        with gr.Tab("🧮 欄位統計"):
            gr.Markdown("### 欄位資訊")
            info_tbl = gr.Dataframe(interactive=False)
            gr.Markdown("### 數值欄位統計 (describe)")
            desc_tbl = gr.Dataframe(interactive=False)

    # ---------- 事件 ----------
    chart_inputs = [state, kind_in, label_in, val_in, val2_in, topn_in]

    load_btn.click(
        load_data,
        inputs=[url_in, verify_cb, dropna_cb],
        outputs=[state, status, cards, table, export_file,
                 col_in, label_in, val_in, val2_in, info_tbl, desc_tbl],
    ).then(make_chart, inputs=chart_inputs, outputs=plot)

    for trig in (search_btn.click, kw_in.submit):
        trig(search, inputs=[state, kw_in, col_in],
             outputs=[table, result_msg, export_file])

    chart_btn.click(make_chart, inputs=chart_inputs, outputs=plot)
    kind_in.change(make_chart, inputs=chart_inputs, outputs=plot)


# ---------- FastAPI：PWA 路由 + 掛載 Gradio ----------
api = FastAPI(title=APP_NAME)
register_pwa(api)  # 必須在 mount 之前


@api.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


app = gr.mount_gradio_app(api, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 7860)),  # Render 會提供 PORT
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
