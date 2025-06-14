from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pandas as pd
import os
from typing import List
from collections import defaultdict
from fastapi import Request
import os
import csv


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
from collections import defaultdict
import os

@app.post("/graph/term/result", response_class=HTMLResponse)
async def graph_term_result(
    request: Request,
    term: str = Form(...),
    work_types: List[str] = Form(...)
):
    # カラーパレット（10色）
    color_list_rgba = [
        "rgba(31, 119, 180, 0.7)", "rgba(255, 127, 14, 0.7)",
        "rgba(44, 160, 44, 0.7)", "rgba(214, 39, 40, 0.7)",
        "rgba(148, 103, 189, 0.7)", "rgba(140, 86, 75, 0.7)",
        "rgba(227, 119, 194, 0.7)", "rgba(127, 127, 127, 0.7)",
        "rgba(188, 189, 34, 0.7)", "rgba(23, 190, 207, 0.7)"
    ]

    # ▼ 通常作業データ読み込み
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
    time_datasets = []
    count_datasets = []

    for idx, wt in enumerate(work_types):
        color = color_list_rgba[idx % len(color_list_rgba)]
        time_data = [result[(ym, wt)]["時間合計"] if (ym, wt) in result else 0 for ym in labels]
        count_data = [result[(ym, wt)]["件数"] if (ym, wt) in result else 0 for ym in labels]
        time_datasets.append({"label": f"{wt}（時間）", "data": time_data, "stack": "main", "backgroundColor": color})
        count_datasets.append({"label": f"{wt}（件数）", "data": count_data, "stack": "main", "backgroundColor": color})

    # ▼ 検査工数データ読み込み（点検及び検査のみ）
    kensa_totals = {}
    if work_types == ["点検及び検査"]:
        kensa_path = os.path.join("data", "検査工数データ.csv")
        try:
            kensa_df = pd.read_csv(kensa_path, encoding="utf-8")
        except UnicodeDecodeError:
            kensa_df = pd.read_csv(kensa_path, encoding="cp932")

        kensa_df.columns = [col.strip() for col in kensa_df.columns]
        kensa_df = kensa_df.rename(columns={
            "作業日": "日付",
            "作業ID": "作業ID",
            "作業実施者": "作業者",
            "作業項目（箇所）": "項目",
            "作業時間": "時間"
        })
        kensa_df["日付"] = pd.to_datetime(kensa_df["日付"], errors="coerce")
        kensa_df["時間"] = pd.to_numeric(kensa_df["時間"], errors="coerce")
        kensa_df = kensa_df.dropna(subset=["日付", "項目", "作業ID"])
        kensa_df["年月"] = kensa_df["日付"].dt.strftime("%Y-%m")
        kensa_df = kensa_df[kensa_df["項目"].isin(["法定検査", "社内検査"])]
        kensa_df = kensa_df.drop_duplicates(subset=["作業ID", "項目"])

        grouped_kensa = kensa_df.groupby(["年月", "項目"]).agg(
            件数=("作業ID", "count"),
            合計時間=("時間", "sum")
        ).reset_index()

        result_kensa = defaultdict(lambda: {"法定検査_件数": 0, "法定検査_時間": 0, "社内検査_件数": 0, "社内検査_時間": 0})
        for _, row in grouped_kensa.iterrows():
            ym = row["年月"]
            if row["項目"] == "法定検査":
                result_kensa[ym]["法定検査_件数"] = row["件数"]
                result_kensa[ym]["法定検査_時間"] = row["合計時間"]
            elif row["項目"] == "社内検査":
                result_kensa[ym]["社内検査_件数"] = row["件数"]
                result_kensa[ym]["社内検査_時間"] = row["合計時間"]

        for ym in labels:
            total_time = result_kensa[ym]["法定検査_時間"] + result_kensa[ym]["社内検査_時間"]
            total_count = result_kensa[ym]["法定検査_件数"] + result_kensa[ym]["社内検査_件数"]
            kensa_totals[ym] = {"時間合計": total_time, "件数合計": total_count}

        # 検査データは2色固定
        time_datasets.append({
            "label": "法定検査",
            "data": [result_kensa[ym]["法定検査_時間"] if ym in result_kensa else 0 for ym in labels],
            "stack": "検査",
            "backgroundColor": "rgba(255, 127, 14, 0.7)"
        })
        time_datasets.append({
            "label": "社内検査",
            "data": [result_kensa[ym]["社内検査_時間"] if ym in result_kensa else 0 for ym in labels],
            "stack": "検査",
            "backgroundColor": "rgba(44, 160, 44, 0.7)"
        })
        count_datasets.append({
            "label": "法定検査",
            "data": [result_kensa[ym]["法定検査_件数"] if ym in result_kensa else 0 for ym in labels],
            "stack": "検査",
            "backgroundColor": "rgba(255, 127, 14, 0.7)"
        })
        count_datasets.append({
            "label": "社内検査",
            "data": [result_kensa[ym]["社内検査_件数"] if ym in result_kensa else 0 for ym in labels],
            "stack": "検査",
            "backgroundColor": "rgba(44, 160, 44, 0.7)"
        })

    return templates.TemplateResponse("graph_term_result.html", {
        "request": request,
        "term": term,
        "labels": labels,
        "time_datasets": time_datasets,
        "count_datasets": count_datasets,
        "work_types": work_types,
        "kensa_totals": kensa_totals
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

from collections import defaultdict
import os

@app.post("/graph/month/result", response_class=HTMLResponse)
async def graph_month_result(
    request: Request,
    year: int = Form(...),
    month: int = Form(...),
    work_types: List[str] = Form(...)
):
    # ▼ カラーパレット
    color_list_rgba = [
        "rgba(31, 119, 180, 0.7)", "rgba(255, 127, 14, 0.7)",
        "rgba(44, 160, 44, 0.7)", "rgba(214, 39, 40, 0.7)",
        "rgba(148, 103, 189, 0.7)", "rgba(140, 86, 75, 0.7)",
        "rgba(227, 119, 194, 0.7)", "rgba(127, 127, 127, 0.7)",
        "rgba(188, 189, 34, 0.7)", "rgba(23, 190, 207, 0.7)"
    ]

    # ▼ CSV読み込み（通常作業データ）
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

    # ▼ 通常作業集計
    result = defaultdict(lambda: {"時間合計": 0.0, "件数": 0})
    for _, row in df.iterrows():
        key = (row["作業者"], row["作業種別"])
        result[key]["時間合計"] += row["時間"]
        result[key]["件数"] += 1

    users = sorted(set(k[0] for k in result))
    time_datasets = []
    count_datasets = []

    for idx, wt in enumerate(work_types):
        color = color_list_rgba[idx % len(color_list_rgba)]
        time_data = [result[(u, wt)]["時間合計"] if (u, wt) in result else 0 for u in users]
        count_data = [result[(u, wt)]["件数"] if (u, wt) in result else 0 for u in users]
        time_datasets.append({"label": f"{wt}（時間）", "data": time_data, "stack": "main", "backgroundColor": color})
        count_datasets.append({"label": f"{wt}（件数）", "data": count_data, "stack": "main", "backgroundColor": color})

    # ▼ 【点検及び検査】のみ選択時の検査データ集計
    kensa_totals = {}
    if work_types == ["点検及び検査"]:
        kensa_path = os.path.join("data", "検査工数データ.csv")
        try:
            kensa_df = pd.read_csv(kensa_path, encoding="utf-8")
        except UnicodeDecodeError:
            kensa_df = pd.read_csv(kensa_path, encoding="cp932")

        kensa_df.columns = [col.strip() for col in kensa_df.columns]
        kensa_df = kensa_df.rename(columns={
            "作業日": "日付",
            "作業ID": "作業ID",
            "作業実施者": "作業者",
            "作業項目（箇所）": "項目",
            "作業時間": "時間"
        })
        kensa_df["日付"] = pd.to_datetime(kensa_df["日付"], errors="coerce")
        kensa_df["時間"] = pd.to_numeric(kensa_df["時間"], errors="coerce")
        kensa_df = kensa_df.dropna(subset=["日付", "作業者", "項目", "時間", "作業ID"])
        kensa_df = kensa_df[(kensa_df["日付"].dt.year == year) & (kensa_df["日付"].dt.month == month)]
        kensa_df = kensa_df[kensa_df["項目"].isin(["法定検査", "社内検査"])]
        kensa_df = kensa_df.drop_duplicates(subset=["作業ID", "項目"])

        grouped_kensa = kensa_df.groupby(["作業者", "項目"]).agg(
            件数=("作業ID", "count"),
            合計時間=("時間", "sum")
        ).reset_index()

        kensa_data = defaultdict(lambda: {"法定検査_時間": 0, "社内検査_時間": 0, "法定検査_件数": 0, "社内検査_件数": 0})
        for _, row in grouped_kensa.iterrows():
            user = row["作業者"]
            if row["項目"] == "法定検査":
                kensa_data[user]["法定検査_時間"] = row["合計時間"]
                kensa_data[user]["法定検査_件数"] = row["件数"]
            elif row["項目"] == "社内検査":
                kensa_data[user]["社内検査_時間"] = row["合計時間"]
                kensa_data[user]["社内検査_件数"] = row["件数"]

        for u in users:
            total_time = kensa_data[u]["法定検査_時間"] + kensa_data[u]["社内検査_時間"]
            total_count = kensa_data[u]["法定検査_件数"] + kensa_data[u]["社内検査_件数"]
            kensa_totals[u] = {"時間合計": total_time, "件数合計": total_count}

        # 検査データは2色固定
        time_datasets.append({
            "label": "法定検査",
            "data": [kensa_data[u]["法定検査_時間"] if u in kensa_data else 0 for u in users],
            "stack": "検査",
            "backgroundColor": "rgba(255, 127, 14, 0.7)"
        })
        time_datasets.append({
            "label": "社内検査",
            "data": [kensa_data[u]["社内検査_時間"] if u in kensa_data else 0 for u in users],
            "stack": "検査",
            "backgroundColor": "rgba(44, 160, 44, 0.7)"
        })
        count_datasets.append({
            "label": "法定検査",
            "data": [kensa_data[u]["法定検査_件数"] if u in kensa_data else 0 for u in users],
            "stack": "検査",
            "backgroundColor": "rgba(255, 127, 14, 0.7)"
        })
        count_datasets.append({
            "label": "社内検査",
            "data": [kensa_data[u]["社内検査_件数"] if u in kensa_data else 0 for u in users],
            "stack": "検査",
            "backgroundColor": "rgba(44, 160, 44, 0.7)"
        })

    return templates.TemplateResponse("graph_month_result.html", {
        "request": request,
        "year": year,
        "month": month,
        "labels": users,
        "time_datasets": time_datasets,
        "count_datasets": count_datasets,
        "work_types": work_types,
        "kensa_totals": kensa_totals
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
from collections import defaultdict
import os
from pandas.tseries.offsets import MonthEnd  # 追加

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
    # ▼ カラーパレット
    color_list_rgba = [
        "rgba(31, 119, 180, 0.7)", "rgba(255, 127, 14, 0.7)",
        "rgba(44, 160, 44, 0.7)", "rgba(214, 39, 40, 0.7)",
        "rgba(148, 103, 189, 0.7)", "rgba(140, 86, 75, 0.7)",
        "rgba(227, 119, 194, 0.7)", "rgba(127, 127, 127, 0.7)",
        "rgba(188, 189, 34, 0.7)", "rgba(23, 190, 207, 0.7)"
    ]

    # ▼ 通常作業データ読み込み
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
    start = pd.to_datetime(f"{start_year}-{start_month:02d}")
    end = pd.to_datetime(f"{end_year}-{end_month:02d}") + MonthEnd(0)  # 修正ポイント！
    df = df[(df["日付"] >= start) & (df["日付"] <= end)]

    grouped = df.groupby(["年月", "作業種別"])
    result = defaultdict(lambda: {"時間合計": 0.0, "件数": 0})
    for (ym, wt), group in grouped:
        result[(ym, wt)]["時間合計"] += group["時間"].sum()
        result[(ym, wt)]["件数"] += len(group)

    ym_labels = sorted(set(ym for ym, _ in result))
    time_datasets = []
    count_datasets = []

    for idx, wt in enumerate(work_types):
        color = color_list_rgba[idx % len(color_list_rgba)]
        time_data = [result[(ym, wt)]["時間合計"] if (ym, wt) in result else 0 for ym in ym_labels]
        count_data = [result[(ym, wt)]["件数"] if (ym, wt) in result else 0 for ym in ym_labels]
        time_datasets.append({"label": f"{wt}（時間）", "data": time_data, "stack": "main", "backgroundColor": color})
        count_datasets.append({"label": f"{wt}（件数）", "data": count_data, "stack": "main", "backgroundColor": color})

    # ▼ 検査工数データ読み込み（点検及び検査のみ）
    kensa_totals = {}
    if work_types == ["点検及び検査"]:
        kensa_path = os.path.join("data", "検査工数データ.csv")
        try:
            kensa_df = pd.read_csv(kensa_path, encoding="utf-8")
        except UnicodeDecodeError:
            kensa_df = pd.read_csv(kensa_path, encoding="cp932")

        kensa_df.columns = [col.strip() for col in kensa_df.columns]
        kensa_df = kensa_df.rename(columns={
            "作業日": "日付",
            "作業ID": "作業ID",
            "作業実施者": "作業者",
            "作業項目（箇所）": "項目",
            "作業時間": "時間"
        })
        kensa_df["日付"] = pd.to_datetime(kensa_df["日付"], errors="coerce")
        kensa_df["時間"] = pd.to_numeric(kensa_df["時間"], errors="coerce")
        kensa_df = kensa_df.dropna(subset=["日付", "項目", "作業ID"])
        kensa_df["年月"] = kensa_df["日付"].dt.strftime("%Y-%m")
        kensa_df = kensa_df[kensa_df["項目"].isin(["法定検査", "社内検査"])]
        kensa_df = kensa_df[kensa_df["作業者"] == user]
        kensa_df = kensa_df[(kensa_df["日付"] >= start) & (kensa_df["日付"] <= end)]
        kensa_df = kensa_df.drop_duplicates(subset=["作業ID", "項目"])

        grouped_kensa = kensa_df.groupby(["年月", "項目"]).agg(
            件数=("作業ID", "count"),
            合計時間=("時間", "sum")
        ).reset_index()

        result_kensa = defaultdict(lambda: {"法定検査_件数": 0, "法定検査_時間": 0, "社内検査_件数": 0, "社内検査_時間": 0})
        for _, row in grouped_kensa.iterrows():
            ym = row["年月"]
            if row["項目"] == "法定検査":
                result_kensa[ym]["法定検査_件数"] = row["件数"]
                result_kensa[ym]["法定検査_時間"] = row["合計時間"]
            elif row["項目"] == "社内検査":
                result_kensa[ym]["社内検査_件数"] = row["件数"]
                result_kensa[ym]["社内検査_時間"] = row["合計時間"]

        for ym in ym_labels:
            total_time = result_kensa[ym]["法定検査_時間"] + result_kensa[ym]["社内検査_時間"]
            total_count = result_kensa[ym]["法定検査_件数"] + result_kensa[ym]["社内検査_件数"]
            kensa_totals[ym] = {"時間合計": total_time, "件数合計": total_count}

        # 検査データ（2色固定）
        time_datasets.append({
            "label": "法定検査",
            "data": [result_kensa[ym]["法定検査_時間"] if ym in result_kensa else 0 for ym in ym_labels],
            "stack": "検査",
            "backgroundColor": "rgba(255, 127, 14, 0.7)"
        })
        time_datasets.append({
            "label": "社内検査",
            "data": [result_kensa[ym]["社内検査_時間"] if ym in result_kensa else 0 for ym in ym_labels],
            "stack": "検査",
            "backgroundColor": "rgba(44, 160, 44, 0.7)"
        })
        count_datasets.append({
            "label": "法定検査",
            "data": [result_kensa[ym]["法定検査_件数"] if ym in result_kensa else 0 for ym in ym_labels],
            "stack": "検査",
            "backgroundColor": "rgba(255, 127, 14, 0.7)"
        })
        count_datasets.append({
            "label": "社内検査",
            "data": [result_kensa[ym]["社内検査_件数"] if ym in result_kensa else 0 for ym in ym_labels],
            "stack": "検査",
            "backgroundColor": "rgba(44, 160, 44, 0.7)"
        })

    return templates.TemplateResponse("graph_person_period_result.html", {
        "request": request,
        "labels": ym_labels,
        "time_datasets": time_datasets,
        "count_datasets": count_datasets,
        "user": user,
        "start": f"{start_year}年{start_month}月",
        "end": f"{end_year}年{end_month}月",
        "work_types": work_types,
        "kensa_totals": kensa_totals
    })

# API連携
@app.post("/api/receive_data")
async def receive_data(request: Request):
    data = await request.json()
    records = data.get("records", [])

    if not records:
        return {"status": "error", "message": "No records found."}

    # 必須フィールドの定義と順序統一
    expected_fields = ["作業ID", "作業日", "作業実施者", "作業項目（箇所）", "作業時間"]
    processed_records = []

    for rec in records:
        row = {key: rec.get(key, "") for key in expected_fields}
        processed_records.append(row)

    # 保存パス
    save_path = os.path.join("data", "検査工数データ.csv")

    # 保存処理（utf-8-sigで日本語対応）
    with open(save_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=expected_fields)
        writer.writeheader()
        writer.writerows(processed_records)

    return {"status": "success", "message": f"{len(processed_records)} records saved to {save_path}"}
