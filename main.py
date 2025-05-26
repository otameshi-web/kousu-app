from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pandas as pd
import os
from typing import List
from collections import defaultdict

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
CSV_PATH = os.path.join("data", "工数データ.csv")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/graph/menu", response_class=HTMLResponse)
async def graph_menu(request: Request):
    return templates.TemplateResponse("graph_menu.html", {"request": request})

@app.get("/graph/all", response_class=HTMLResponse)
async def graph_all_menu(request: Request):
    return templates.TemplateResponse("graph_all_menu.html", {"request": request})
@app.get("/graph/term", response_class=HTMLResponse)
async def graph_term(request: Request):
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="cp932")
    df.columns = [col.strip() for col in df.columns]
    df = df.rename(columns={"作業日": "日付", "作業実施者": "作業者", "作業種別": "作業種別", "作業時間": "時間"})
    df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
    df = df.dropna(subset=["日付", "作業種別"])

    def get_term(date):
        y = date.year
        return f"{y-1}年5月～{y}年4月" if date.month < 5 else f"{y}年5月～{y+1}年4月"
    df["期"] = df["日付"].apply(get_term)

    term_list = sorted(df["期"].unique(), reverse=True)
    work_types = sorted([w for w in df["作業種別"].unique() if w != "小計"])

    return templates.TemplateResponse("graph_term.html", {
        "request": request,
        "terms": term_list,
        "work_types": work_types
    })
@app.post("/graph/term/result", response_class=HTMLResponse)
async def graph_term_result(
    request: Request,
    term: str = Form(...),
    work_types: List[str] = Form(...)
):
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="cp932")

    df.columns = [col.strip() for col in df.columns]
    df = df.rename(columns={
        "作業日": "日付",
        "作業実施者": "作業者",
        "作業種別": "作業種別",
        "作業時間": "時間"
    })

    df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
    df = df.dropna(subset=["日付", "作業種別", "作業者", "時間"])
    df["時間"] = pd.to_numeric(df["時間"], errors="coerce")
    df = df.dropna()

    def get_term(date):
        y = date.year
        return f"{y-1}年5月～{y}年4月" if date.month < 5 else f"{y}年5月～{y+1}年4月"

    df["期"] = df["日付"].apply(get_term)
    df = df[df["期"] == term]
    df = df[df["作業種別"].isin(work_types)]
    df = df[~df["作業者"].str.contains("削除済み", na=False)]

    df["年月"] = df["日付"].dt.strftime("%Y-%m")
    grouped = df.groupby(["年月", "作業種別"])

    result = defaultdict(lambda: {"時間合計": 0.0, "件数": 0})
    for (ym, wt), group in grouped:
        result[(ym, wt)]["時間合計"] += group["時間"].sum()
        result[(ym, wt)]["件数"] += len(group)

    labels = sorted(set(ym for ym, _ in result))
    datasets = []
    max_time = 0
    max_count = 0

    for wt in work_types:
        time_data = [result[(ym, wt)]["時間合計"] if (ym, wt) in result else 0 for ym in labels]
        count_data = [result[(ym, wt)]["件数"] if (ym, wt) in result else 0 for ym in labels]
        datasets.append({"label": f"{wt}（時間）", "data": time_data})
        datasets.append({"label": f"{wt}（件数）", "data": count_data})

        max_time = max(max_time, max(time_data, default=0))
        max_count = max(max_count, max(count_data, default=0))

    # 上限を少し余裕をもって設定（10%増し）
    suggested_max_time = round(max_time * 1.1, 1)
    suggested_max_count = int(max_count * 1.1 + 1)

    return templates.TemplateResponse("graph_term_result.html", {
        "request": request,
        "term": term,
        "labels": labels,
        "datasets": datasets,
        "suggested_max_time": suggested_max_time,
        "suggested_max_count": suggested_max_count
    })

# ==========================
# Part 3: 月別・個人比較関連
# ==========================

@app.get("/graph/month", response_class=HTMLResponse)
async def graph_month(request: Request):
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="cp932")
    df.columns = [col.strip() for col in df.columns]
    df = df.rename(columns={"作業日": "日付", "作業実施者": "作業者", "作業種別": "作業種別", "作業時間": "時間"})
    df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
    df = df.dropna(subset=["日付", "作業種別"])

    df["年"] = df["日付"].dt.year
    df["月"] = df["日付"].dt.month
    work_types = sorted([w for w in df["作業種別"].unique() if w != "小計"])
    years = sorted(df["年"].unique(), reverse=True)
    months = sorted(df["月"].unique())

    return templates.TemplateResponse("graph_month.html", {
        "request": request,
        "years": years,
        "months": months,
        "work_types": work_types
    })

@app.post("/graph/month/result", response_class=HTMLResponse)
async def graph_month_result(request: Request, year: int = Form(...), month: int = Form(...), work_types: List[str] = Form(...)):
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="cp932")
    df.columns = [col.strip() for col in df.columns]
    df = df.rename(columns={"作業日": "日付", "作業実施者": "作業者", "作業種別": "作業種別", "作業時間": "時間"})
    df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
    df["時間"] = pd.to_numeric(df["時間"], errors="coerce")
    df = df.dropna(subset=["日付", "作業者", "作業種別", "時間"])

    df = df[(df["日付"].dt.year == year) & (df["日付"].dt.month == month)]
    df = df[df["作業種別"].isin(work_types)]
    df = df[~df["作業者"].str.contains("削除済み", na=False)]

    result = defaultdict(lambda: {"時間合計": 0.0, "件数": 0})
    for _, row in df.iterrows():
        key = (row["作業者"], row["作業種別"])
        result[key]["時間合計"] += row["時間"]
        result[key]["件数"] += 1

    users = sorted(set(k[0] for k in result))
    datasets = []
    for wt in work_types:
        time_data = [result[(u, wt)]["時間合計"] if (u, wt) in result else 0 for u in users]
        count_data = [result[(u, wt)]["件数"] if (u, wt) in result else 0 for u in users]
        datasets.append({"label": f"{wt}（時間）", "data": time_data})
        datasets.append({"label": f"{wt}（件数）", "data": count_data})

    return templates.TemplateResponse("graph_month_result.html", {
        "request": request,
        "year": year,
        "month": month,
        "labels": users,
        "datasets": datasets
    })


# ==========================
# Part 4: 個人グラフ処理
# ==========================

@app.get("/graph/person", response_class=HTMLResponse)
async def graph_person_menu(request: Request):
    return templates.TemplateResponse("graph_person_menu.html", {"request": request})

@app.get("/graph/person/type", response_class=HTMLResponse)
async def graph_person_type_input(request: Request):
    try:
        try:
            df = pd.read_csv(CSV_PATH, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(CSV_PATH, encoding="cp932")

        df.columns = [col.strip() for col in df.columns]
        df = df.rename(columns={
            "作業日": "日付",
            "作業実施者": "作業者",
            "作業種別": "作業種別",
            "作業時間": "時間"
        })

        df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
        df = df.dropna(subset=["日付", "作業者"])

        df["年"] = df["日付"].dt.year
        df["月"] = df["日付"].dt.month

        years = sorted(df["年"].unique(), reverse=True)
        months = list(range(1, 13))
        users = sorted(df["作業者"].dropna().unique())
        users = [u for u in users if "削除済み" not in u]

        return templates.TemplateResponse("graph_person_type.html", {
            "request": request,
            "years": years,
            "months": months,
            "users": users
        })

    except Exception as e:
        return HTMLResponse(f"エラー: {e}", status_code=500)


# 作業種別比較表（表示）
# 作業種別比較表（表示）
@app.post("/graph/person/type/result", response_class=HTMLResponse)
async def graph_person_type_result(
    request: Request,
    year: int = Form(...),
    month: int = Form(...),
    user: str = Form(...)
):
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="cp932")

    df.columns = [col.strip() for col in df.columns]
    df = df.rename(columns={
        "作業日": "日付", "作業実施者": "作業者",
        "作業種別": "作業種別", "作業時間": "時間"
    })
    df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
    df["時間"] = pd.to_numeric(df["時間"], errors="coerce")
    df = df.dropna(subset=["日付", "作業者", "作業種別", "時間"])

    df = df[
        (df["日付"].dt.year == year) &
        (df["日付"].dt.month == month) &
        (df["作業者"] == user)
    ]
    df = df[df["作業種別"] != "小計"]

    grouped = df.groupby("作業種別")
    result = {
        wt: {
            "時間合計": float(group["時間"].sum()),
            "件数": int(len(group))
        }
        for wt, group in grouped
    }

    # 合計データを追加
    total_time = sum(item["時間合計"] for item in result.values())
    total_count = sum(item["件数"] for item in result.values())
    result["合計"] = {
        "時間合計": total_time,
        "件数": total_count
    }

    labels = list(result.keys())
    time_data = [result[wt]["時間合計"] for wt in labels]
    count_data = [result[wt]["件数"] for wt in labels]

    datasets = [
        {"label": "時間（h）", "data": time_data},
        {"label": "件数（件）", "data": count_data}
    ]

    return templates.TemplateResponse("graph_person_type_result.html", {
        "request": request,
        "labels": labels,
        "datasets": datasets,
        "year": year,
        "month": month,
        "user": user
    })

@app.get("/graph/person/period", response_class=HTMLResponse)
async def graph_person_period_input(request: Request):
    try:
        try:
            df = pd.read_csv(CSV_PATH, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(CSV_PATH, encoding="cp932")

        df.columns = [col.strip() for col in df.columns]
        df = df.rename(columns={
            "作業日": "日付",
            "作業実施者": "作業者",
            "作業種別": "作業種別",
            "作業時間": "時間"
        })

        df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
        df = df.dropna(subset=["日付", "作業者", "作業種別"])

        df["年"] = df["日付"].dt.year
        df["月"] = df["日付"].dt.month

        years = sorted(df["年"].unique(), reverse=True)
        months = list(range(1, 13))
        users = sorted(df["作業者"].dropna().unique())
        users = [u for u in users if "削除済み" not in u]

        work_types = sorted(df["作業種別"].unique())
        work_types = [w for w in work_types if w != "小計"]

        return templates.TemplateResponse("graph_person_period.html", {
            "request": request,
            "years": years,
            "months": months,
            "users": users,
            "work_types": work_types
        })

    except Exception as e:
        return HTMLResponse(f"エラー：{e}", status_code=500)

# 期間指定比較表（表示）
@app.post("/graph/person/period/result", response_class=HTMLResponse)
async def graph_person_period_result(
    request: Request,
    start_year: int = Form(...),
    start_month: int = Form(...),
    end_year: int = Form(...),
    end_month: int = Form(...),
    user: str = Form(...),
    work_types: List[str] = Form(...)
):
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="cp932")

    df.columns = [col.strip() for col in df.columns]
    df = df.rename(columns={
        "作業日": "日付", "作業実施者": "作業者",
        "作業種別": "作業種別", "作業時間": "時間"
    })

    df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
    df["時間"] = pd.to_numeric(df["時間"], errors="coerce")
    df = df.dropna(subset=["日付", "作業者", "作業種別", "時間"])

    df = df[df["作業者"] == user]
    df = df[df["作業種別"].isin(work_types)]
    df = df[df["作業種別"] != "小計"]

    df["年月"] = df["日付"].dt.strftime("%Y-%m")
    df["年"] = df["日付"].dt.year
    df["月"] = df["日付"].dt.month

    start = pd.to_datetime(f"{start_year}-{start_month:02d}")
    end = pd.to_datetime(f"{end_year}-{end_month:02d}")
    df = df[(df["日付"] >= start) & (df["日付"] <= end)]

    grouped = df.groupby(["年月", "作業種別"])
    result = defaultdict(lambda: {"時間合計": 0.0, "件数": 0})
    for (ym, wt), group in grouped:
        result[(ym, wt)]["時間合計"] += group["時間"].sum()
        result[(ym, wt)]["件数"] += len(group)

    ym_labels = sorted(set(ym for ym, _ in result))
    datasets = []
    for wt in work_types:
        time_data = [result[(ym, wt)]["時間合計"] if (ym, wt) in result else 0 for ym in ym_labels]
        count_data = [result[(ym, wt)]["件数"] if (ym, wt) in result else 0 for ym in ym_labels]
        datasets.append({"label": f"{wt}（時間）", "data": time_data})
        datasets.append({"label": f"{wt}（件数）", "data": count_data})

    return templates.TemplateResponse("graph_person_period_result.html", {
        "request": request,
        "labels": ym_labels,
        "datasets": datasets,
        "user": user,
        "start": f"{start_year}年{start_month}月",
        "end": f"{end_year}年{end_month}月"
    })
