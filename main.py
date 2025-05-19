from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
import pandas as pd
import chardet  # 🔸文字コード判定ライブラリ

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

CSV_PATH = os.path.join("data", "工数データ.csv")

def detect_encoding(file_path):
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read(10000))
        return result['encoding']

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/graph", response_class=HTMLResponse)
async def read_graph(request: Request):
    try:
        encoding = detect_encoding(CSV_PATH)
        df = pd.read_csv(CSV_PATH, encoding=encoding)
        df.columns = [col.strip() for col in df.columns]
        df = df.dropna(subset=["日付", "作業者", "作業種別", "時間"])
        df["時間"] = pd.to_numeric(df["時間"], errors="coerce")
        df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
        df = df.dropna()

        pivot = df.pivot_table(
            index="作業者",
            columns="作業種別",
            values="時間",
            aggfunc="sum",
            fill_value=0
        )

        labels = list(pivot.index)
        datasets = [
            {
                "label": col,
                "data": [float(pivot.at[idx, col]) for idx in labels]
            }
            for col in pivot.columns
        ]

        return templates.TemplateResponse("graph.html", {
            "request": request,
            "labels": labels,
            "datasets": datasets
        })

    except Exception as e:
        return f"❌ データ処理エラー: {str(e)}"
