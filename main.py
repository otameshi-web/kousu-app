from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pandas as pd
import os

app = FastAPI()

# 静的ファイルとテンプレートのパス指定
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# CSVファイルのパス
CSV_PATH = os.path.join("data", "工数データ.csv")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/graph", response_class=HTMLResponse)
async def read_graph(request: Request):
    try:
        # UTF-8で読み込み（失敗したら Shift_JISで再挑戦）
        try:
            df = pd.read_csv(CSV_PATH, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(CSV_PATH, encoding="cp932")
    except Exception as e:
        return f"CSV読み込みエラー: {str(e)}"

    try:
        # 列名を標準化（スペース除去）
        df.columns = [col.strip() for col in df.columns]

        # 列名変換マップ（仮→実データ）
        rename_map = {
            "作業日": "日付",
            "作業実施者": "作業者",
            "作業種別": "作業種別",
            "作業時間": "時間"
        }
        df = df.rename(columns=rename_map)

        # 必須列が存在するかチェック
        required = ["日付", "作業者", "作業種別", "時間"]
        for col in required:
            if col not in df.columns:
                return f"❌ 必須列が不足しています: {col}"

        # 前処理
        df = df.dropna(subset=required)
        df["時間"] = pd.to_numeric(df["時間"], errors="coerce")
        df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
        df = df.dropna()

        # ピボット集計
        pivot = df.pivot_table(
            index="作業者",
            columns="作業種別",
            values="時間",
            aggfunc="sum",
            fill_value=0
        )

        # グラフ用データ変換（floatに変換）
        labels = list(pivot.index)
        datasets = [
            {
                "label": col,
                "data": [float(pivot.at[idx, col]) if col in pivot.columns else 0.0 for idx in labels]
            }
            for col in pivot.columns
        ]

        return templates.TemplateResponse("graph.html", {
            "request": request,
            "labels": labels,
            "datasets": datasets
        })

    except Exception as e:
        return f"データ処理エラー: {str(e)}"

@app.get("/graph/menu", response_class=HTMLResponse)
async def graph_menu(request: Request):
    return templates.TemplateResponse("graph_menu.html", {"request": request})
