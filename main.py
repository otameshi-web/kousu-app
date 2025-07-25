from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List
import pandas as pd
import os
import io
import base64
import requests
from datetime import datetime
from collections import defaultdict
import re
from fastapi.responses import RedirectResponse
from pathlib import Path

# === 基本設定 ===
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
CSV_PATH = os.path.join("data", "工数データ.csv")

# === グラフUI系ルート ===
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/graph/general")
async def general_graph_menu(request: Request):
    return templates.TemplateResponse("graph_general_menu.html", {"request": request})

@app.get("/graph/estimate/menu")
async def estimate_graph_menu(request: Request):
    return templates.TemplateResponse("graph_estimate_menu.html", {"request": request})

@app.get("/graph/estimate/person", response_class=HTMLResponse)
async def graph_estimate_person_menu(request: Request):
    return templates.TemplateResponse("graph_estimate_person_menu.html", {"request": request})

@app.get("/graph/estimate/total", response_class=HTMLResponse)
async def graph_estimate_total_menu(request: Request):
    return templates.TemplateResponse("graph_estimate_total_menu.html", {"request": request})

@app.get("/graph/estimate/person/term", response_class=HTMLResponse)
async def graph_estimate_person_term(request: Request):
    csv_path = os.path.join("data", "一般工事売上データ.csv")

    # ▼ CSV読み込み（文字コードの自動切替）
    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    # ▼ 作成日列から有効な期（データが存在する）だけを選択肢に追加
    try:
        df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
        df = df.dropna(subset=["作成日"])  # 作成日が無効な行は除外

        min_date = df["作成日"].min()
        max_date = df["作成日"].max()

        start_year = min_date.year if min_date.month >= 5 else min_date.year - 1
        end_year = max_date.year if max_date.month >= 5 else max_date.year - 1

        periods = []
        for year in range(start_year, end_year + 1):
            term_start = pd.Timestamp(year=year, month=5, day=1)
            term_end = pd.Timestamp(year=year + 1, month=4, day=30)
            if not df[(df["作成日"] >= term_start) & (df["作成日"] <= term_end)].empty:
                periods.append(f"{year}年5月～{year+1}年4月")

    except Exception as e:
        return HTMLResponse(content=f"<h3>期情報の取得失敗: {e}</h3>", status_code=500)

    # ▼ 担当者プルダウン生成（削除済み除外）
    if "担当者名" in df.columns:
        persons = sorted([p for p in df["担当者名"].dropna().unique() if "削除済み" not in p])
    else:
        persons = []

    return templates.TemplateResponse("graph_estimate_person_term.html", {
        "request": request,
        "periods": periods,
        "persons": persons
    })

# エンドポイント：期毎グラフ（見積金額集計）
@app.post("/graph/estimate/person/term/result", response_class=HTMLResponse)
async def graph_estimate_person_term_result(request: Request):
    form = await request.form()
    term = form.get("term")
    person = form.get("person")

    if not term or not person:
        return HTMLResponse(content="<h3>フォームデータの取得失敗: term または person が空です</h3>", status_code=400)

    csv_path = os.path.join("data", "一般工事売上データ.csv")
    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    try:
        df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
        df["決定日"] = pd.to_datetime(df["決定日"], errors="coerce")
        y1 = int(term[:4])
        start = pd.Timestamp(f"{y1}-05-01")
        end = pd.Timestamp(f"{y1 + 1}-04-30")
    except Exception as e:
        return HTMLResponse(content=f"<h3>日付処理失敗: {e}</h3>", status_code=500)

    # ▼ 担当者フィルタ共通
    df = df[df["担当者名"] == person]

    # ▼ 月ラベル
    months_range = pd.date_range(start=start, periods=12, freq="MS")
    months = [f"{d.year}年{d.month}月" for d in months_range]

    # ▼ 金額集計：見積（作成日）
    df_est = df[(df["作成日"] >= start) & (df["作成日"] <= end)].sort_values("作成日")
    df_est = df_est.drop_duplicates("工事見積No.", keep="last")
    df_est["年月"] = df_est["作成日"].dt.to_period("M").dt.to_timestamp()

    summary_est = df_est.groupby("年月").agg(金額合計=("小計", "sum"), 件数=("工事見積No.", "count"))
    summary_est = summary_est.reindex(months_range, fill_value=0)

    estimate_amounts = summary_est["金額合計"].astype(int).tolist()
    estimate_counts = summary_est["件数"].astype(int).tolist()

    # ▼ 金額集計：決定（決定日）
    df_dec = df[(df["決定日"].notna()) & (df["決定日"] >= start) & (df["決定日"] <= end)]
    df_dec = df_dec.sort_values("決定日").drop_duplicates("工事見積No.", keep="last")
    df_dec["年月"] = df_dec["決定日"].dt.to_period("M").dt.to_timestamp()

    summary_dec = df_dec.groupby("年月").agg(金額合計=("小計", "sum"), 件数=("工事見積No.", "count"))
    summary_dec = summary_dec.reindex(months_range, fill_value=0)

    decision_amounts = summary_dec["金額合計"].astype(int).tolist()
    decision_counts = summary_dec["件数"].astype(int).tolist()

    # ▼ 合計金額と平均単価（フォーマット付き）
    estimate_total_raw = sum(estimate_amounts)
    decision_total_raw = sum(decision_amounts)
    total_estimate_count = sum(estimate_counts)
    total_decision_count = sum(decision_counts)
    estimate_per_case_raw = estimate_total_raw // total_estimate_count if total_estimate_count > 0 else 0

    estimate_total = f"{estimate_total_raw:,}"
    decision_total = f"{decision_total_raw:,}"
    estimate_per_case = f"{estimate_per_case_raw:,}"
    
    # ▼ 決定率（%表記）
    money_decision_rate = f"{(decision_total_raw / estimate_total_raw * 100):.1f}%" if estimate_total_raw > 0 else "0%"
    count_decision_rate = f"{(total_decision_count / total_estimate_count * 100):.1f}%" if total_estimate_count > 0 else "0%"


    return templates.TemplateResponse("graph_estimate_person_term_result.html", {
        "request": request,
        "term": term,
        "person": person,
        "months": months,
        "estimate_amounts": estimate_amounts,
        "estimate_counts": estimate_counts,
        "decision_amounts": decision_amounts,
        "decision_counts": decision_counts,
        "estimate_total": estimate_total,
        "decision_total": decision_total,
        "estimate_per_case": estimate_per_case,
        "money_decision_rate": money_decision_rate,
        "count_decision_rate": count_decision_rate

    })

# --- 追加：月別棒グラフクリック時の詳細ページ表示 ---

@app.get("/graph/estimate/person/term/detail", response_class=HTMLResponse)
async def graph_estimate_detail_result(
    request: Request,
    term: str,
    person: str,
    year: int,
    month: int,
    type: str  # "estimate" または "decision"
):
    csv_path = os.path.join("data", "一般工事売上データ.csv")

    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    try:
        df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
        df["決定日"] = pd.to_datetime(df["決定日"], errors="coerce")
    except Exception as e:
        return HTMLResponse(content=f"<h3>日付変換エラー: {e}</h3>", status_code=500)

    # ▼ 期を日付で範囲化
    y1 = int(term[:4])
    start = pd.Timestamp(f"{y1}-05-01")
    end = pd.Timestamp(f"{y1 + 1}-04-30")

    # ▼ 抽出用カラム
    date_column = "作成日" if type == "estimate" else "決定日"
    label_prefix = "見積作成" if type == "estimate" else "決定見積"
    date_label = "作成日" if type == "estimate" else "決定日"

    # ▼ 担当者・日付・期フィルタ
    df_month = df[
        (df["担当者名"] == person) &
        (df[date_column].notna()) &
        (df[date_column].dt.year == year) &
        (df[date_column].dt.month == month) &
        (df[date_column] >= start) &
        (df[date_column] <= end)
    ]

    # ▼ 工事見積No単位で詳細と小計を結合
    grouped = df_month.groupby("工事見積No.")

    records = []
    for no, group in grouped:
        row = group.iloc[0]
        record = {
            "date": row[date_column].strftime("%Y年%m月%d日"),
            "id": row["工事見積No."],
            "name": row["建物名"],
            "details": "・".join(group["詳細"].dropna().astype(str)),
            "amount": int(row["小計"])
        }
        records.append(record)

    # ▼ タイトル
    title = f"{year}年{month}月の{label_prefix}データ一覧（{person}）"

    return templates.TemplateResponse("graph_estimate_detail_result.html", {
        "request": request,
        "title": title,
        "records": records,
        "total_amount": sum(r["amount"] for r in records),
        "date_label": date_label  # ← 表ヘッダーに表示する日付種別
    })

@app.get("/graph/estimate/person/period", response_class=HTMLResponse)
async def graph_estimate_person_period(request: Request):
    csv_path = os.path.join("data", "一般工事売上データ.csv")

    # ▼ CSV読み込み（文字コードの自動切替）
    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    # ▼ 作成日から年月リスト生成（yyyy年m月 形式）
    try:
        df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
        df = df.dropna(subset=["作成日"])
        months = sorted(df["作成日"].dt.to_period("M").unique())
        all_months = [f"{m.year}年{m.month}月" for m in months]
    except Exception as e:
        return HTMLResponse(content=f"<h3>年月リストの生成失敗: {e}</h3>", status_code=500)

    # ▼ 担当者名（削除済みは除外）
    if "担当者名" in df.columns:
        persons = sorted([p for p in df["担当者名"].dropna().unique() if "削除済み" not in p])
    else:
        persons = []

    return templates.TemplateResponse("graph_estimate_person_period.html", {
        "request": request,
        "all_months": all_months,
        "persons": persons
    })

@app.post("/graph/estimate/person/period/result", response_class=HTMLResponse)
async def graph_estimate_person_period_result(request: Request):
    form = await request.form()
    start_str = form.get("start_month")  # 例: 2024年6月
    end_str = form.get("end_month")
    person = form.get("person")

    if not start_str or not end_str or not person:
        return HTMLResponse(content="<h3>フォームデータの取得失敗: start, end, person のいずれかが空です</h3>", status_code=400)

    # 「2025年7月」→ Timestamp("2025-07-01")
    def parse_ym_to_date(ym: str) -> pd.Timestamp:
        m = re.match(r"(\d{4})年(\d{1,2})月", ym)
        if m:
            year, month = m.groups()
            return pd.Timestamp(f"{year}-{int(month):02d}-01")
        else:
            raise ValueError(f"無効な年月形式: {ym}")

    try:
        start = parse_ym_to_date(start_str)
        end = parse_ym_to_date(end_str) + pd.offsets.MonthEnd(0)  # 月末日まで含める
    except Exception as e:
        return HTMLResponse(content=f"<h3>日付変換エラー: {e}</h3>", status_code=400)

    csv_path = os.path.join("data", "一般工事売上データ.csv")
    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    try:
        df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
        df["決定日"] = pd.to_datetime(df["決定日"], errors="coerce")
    except Exception as e:
        return HTMLResponse(content=f"<h3>日付処理失敗: {e}</h3>", status_code=500)

    df = df[df["担当者名"] == person]

    months_range = pd.date_range(start=start, end=end, freq="MS")
    months = [f"{d.year}年{d.month}月" for d in months_range]

    # ▼ 見積金額（作成日）
    df_est = df[(df["作成日"] >= start) & (df["作成日"] <= end)].sort_values("作成日")
    df_est = df_est.drop_duplicates("工事見積No.", keep="last")
    df_est["年月"] = df_est["作成日"].dt.to_period("M").dt.to_timestamp()

    summary_est = df_est.groupby("年月").agg(金額合計=("小計", "sum"), 件数=("工事見積No.", "count"))
    summary_est = summary_est.reindex(months_range, fill_value=0)

    estimate_amounts = summary_est["金額合計"].astype(int).tolist()
    estimate_counts = summary_est["件数"].astype(int).tolist()

    # ▼ 決定金額（決定日）
    df_dec = df[(df["決定日"].notna()) & (df["決定日"] >= start) & (df["決定日"] <= end)]
    df_dec = df_dec.sort_values("決定日").drop_duplicates("工事見積No.", keep="last")
    df_dec["年月"] = df_dec["決定日"].dt.to_period("M").dt.to_timestamp()

    summary_dec = df_dec.groupby("年月").agg(金額合計=("小計", "sum"), 件数=("工事見積No.", "count"))
    summary_dec = summary_dec.reindex(months_range, fill_value=0)

    decision_amounts = summary_dec["金額合計"].astype(int).tolist()
    decision_counts = summary_dec["件数"].astype(int).tolist()

    # ▼ 合計金額・平均単価
    estimate_total_raw = sum(estimate_amounts)
    decision_total_raw = sum(decision_amounts)
    total_estimate_count = sum(estimate_counts)
    total_decision_count = sum(decision_counts)
    estimate_per_case_raw = estimate_total_raw // total_estimate_count if total_estimate_count > 0 else 0

    estimate_total = f"{estimate_total_raw:,}"
    decision_total = f"{decision_total_raw:,}"
    estimate_per_case = f"{estimate_per_case_raw:,}"

    money_decision_rate = f"{(decision_total_raw / estimate_total_raw * 100):.1f}%" if estimate_total_raw > 0 else "0%"
    count_decision_rate = f"{(total_decision_count / total_estimate_count * 100):.1f}%" if total_estimate_count > 0 else "0%"

    return templates.TemplateResponse("graph_estimate_person_period_result.html", {
        "request": request,
        "start": start_str,
        "end": end_str,
        "start_month": start_str,
        "end_month": end_str,
        "person": person,
        "months": months,
        "estimate_amounts": estimate_amounts,
        "estimate_counts": estimate_counts,
        "decision_amounts": decision_amounts,
        "decision_counts": decision_counts,
        "estimate_total": estimate_total,
        "decision_total": decision_total,
        "estimate_per_case": estimate_per_case,
        "money_decision_rate": money_decision_rate,
        "count_decision_rate": count_decision_rate
    })

@app.get("/graph/estimate/person/period/detail", response_class=HTMLResponse)
async def graph_estimate_person_period_detail(
    request: Request,
    start: str,
    end: str,
    year: int,
    month: int,
    person: str,
    type: str  # 'estimate' または 'decision'
):
    import os
    csv_path = os.path.join("data", "一般工事売上データ.csv")

    # CSV読み込み（エンコーディング対応）
    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
    df["決定日"] = pd.to_datetime(df["決定日"], errors="coerce")

    # ▼ 動的に日付・タイトル設定
    date_column = "作成日" if type == "estimate" else "決定日"
    label_prefix = "見積作成" if type == "estimate" else "決定見積"
    date_label = "作成日" if type == "estimate" else "決定日"

    # ▼ 担当者・年月フィルタ
    df = df[
        (df["担当者名"] == person) &
        (df[date_column].notna()) &
        (df[date_column].dt.year == year) &
        (df[date_column].dt.month == month)
    ]

    # ▼ 工事見積No単位で集計
    grouped = df.groupby("工事見積No.")

    records = []
    for no, group in grouped:
        row = group.iloc[0]
        record = {
            "date": row[date_column].strftime("%Y年%m月%d日"),
            "id": row["工事見積No."],
            "name": row["建物名"],
            "details": "・".join(group["詳細"].dropna().astype(str)),
            "amount": int(row["小計"])
        }
        records.append(record)

    title = f"{year}年{month}月の{label_prefix}データ一覧（{person}）"

    return templates.TemplateResponse("graph_estimate_person_period_detail_result.html", {
        "request": request,
        "title": title,
        "records": records,
        "total_amount": sum([r["amount"] for r in records]),
        "start": start,
        "end": end,
        "date_label": date_label  # ← テンプレートに渡す
    })

@app.get("/graph/estimate/total/term", response_class=HTMLResponse)
async def graph_estimate_total_term(request: Request):
    csv_path = os.path.join("data", "一般工事売上データ.csv")

    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    try:
        df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
        df = df.dropna(subset=["作成日"])

        min_date = df["作成日"].min()
        max_date = df["作成日"].max()

        start_year = min_date.year if min_date.month >= 5 else min_date.year - 1
        end_year = max_date.year if max_date.month >= 5 else max_date.year - 1

        periods = []
        for year in range(start_year, end_year + 1):
            term_start = pd.Timestamp(year=year, month=5, day=1)
            term_end = pd.Timestamp(year=year + 1, month=4, day=30)
            if not df[(df["作成日"] >= term_start) & (df["作成日"] <= term_end)].empty:
                periods.append(f"{year}年5月～{year+1}年4月")
    except Exception as e:
        return HTMLResponse(content=f"<h3>期情報の取得失敗: {e}</h3>", status_code=500)

    return templates.TemplateResponse("graph_estimate_total_term.html", {
        "request": request,
        "periods": periods
    })

@app.post("/graph/estimate/total/term/result", response_class=HTMLResponse)
async def graph_estimate_total_term_result(request: Request, term: str = Form(...)):
    csv_path = os.path.join("data", "一般工事売上データ.csv")

    # ▼ CSV読み込み（文字コードの自動切替）
    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    # ▼ 日付・期間変換
    try:
        df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
        df["決定日"] = pd.to_datetime(df["決定日"], errors="coerce")

        y1 = int(term[:4])
        start = pd.Timestamp(f"{y1}-05-01")
        end = pd.Timestamp(f"{y1 + 1}-04-30")
    except Exception as e:
        return HTMLResponse(content=f"<h3>日付処理失敗: {e}</h3>", status_code=500)

    # ▼ 月ラベル（5月～翌年4月）
    months_range = pd.date_range(start=start, periods=12, freq="MS")
    months = [f"{d.year}年{d.month}月" for d in months_range]

    # ▼ 見積金額集計（作業日が対象）
    df_est = df[(df["作成日"] >= start) & (df["作成日"] <= end)].sort_values("作成日")
    df_est = df_est.drop_duplicates("工事見積No.", keep="last")
    df_est["年月"] = df_est["作成日"].dt.to_period("M").dt.to_timestamp()

    summary_est = df_est.groupby("年月").agg(金額合計=("小計", "sum"), 件数=("工事見積No.", "count"))
    summary_est = summary_est.reindex(months_range, fill_value=0)

    estimate_amounts = summary_est["金額合計"].astype(int).tolist()
    estimate_counts = summary_est["件数"].astype(int).tolist()

    # ▼ 決定金額集計（決定日が対象）
    df_dec = df[(df["決定日"].notna()) & (df["決定日"] >= start) & (df["決定日"] <= end)]
    df_dec = df_dec.sort_values("決定日").drop_duplicates("工事見積No.", keep="last")
    df_dec["年月"] = df_dec["決定日"].dt.to_period("M").dt.to_timestamp()

    summary_dec = df_dec.groupby("年月").agg(金額合計=("小計", "sum"), 件数=("工事見積No.", "count"))
    summary_dec = summary_dec.reindex(months_range, fill_value=0)

    decision_amounts = summary_dec["金額合計"].astype(int).tolist()
    decision_counts = summary_dec["件数"].astype(int).tolist()

    # ▼ 合計・平均・決定率の計算
    estimate_total_raw = sum(estimate_amounts)
    decision_total_raw = sum(decision_amounts)
    total_estimate_count = sum(estimate_counts)
    total_decision_count = sum(decision_counts)
    estimate_per_case_raw = estimate_total_raw // total_estimate_count if total_estimate_count > 0 else 0

    estimate_total = f"{estimate_total_raw:,}"
    decision_total = f"{decision_total_raw:,}"
    estimate_per_case = f"{estimate_per_case_raw:,}"

    money_decision_rate = f"{(decision_total_raw / estimate_total_raw * 100):.1f}%" if estimate_total_raw > 0 else "0%"
    count_decision_rate = f"{(total_decision_count / total_estimate_count * 100):.1f}%" if total_estimate_count > 0 else "0%"

    return templates.TemplateResponse("graph_estimate_total_term_result.html", {
        "request": request,
        "term": term,
        "months": months,
        "estimate_amounts": estimate_amounts,
        "decision_amounts": decision_amounts,
        "estimate_counts": estimate_counts,
        "decision_counts": decision_counts,
        "estimate_total": estimate_total,
        "decision_total": decision_total,
        "estimate_per_case": estimate_per_case,
        "money_decision_rate": money_decision_rate,
        "count_decision_rate": count_decision_rate
    })

@app.get("/graph/estimate/total/compare", response_class=HTMLResponse)
async def graph_estimate_total_compare(request: Request):
    csv_path = os.path.join("data", "一般工事売上データ.csv")

    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    try:
        df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
        df = df.dropna(subset=["作成日"])

        min_date = df["作成日"].min()
        max_date = df["作成日"].max()

        start_year = min_date.year if min_date.month >= 5 else min_date.year - 1
        end_year = max_date.year if max_date.month >= 5 else max_date.year - 1

        periods = []
        for year in range(start_year, end_year + 1):
            term_start = pd.Timestamp(year=year, month=5, day=1)
            term_end = pd.Timestamp(year=year + 1, month=4, day=30)
            if not df[(df["作成日"] >= term_start) & (df["作成日"] <= term_end)].empty:
                periods.append(f"{year}年5月～{year+1}年4月")
    except Exception as e:
        return HTMLResponse(content=f"<h3>期情報の取得失敗: {e}</h3>", status_code=500)

    return templates.TemplateResponse("graph_estimate_total_compare.html", {
        "request": request,
        "periods": periods
    })

@app.post("/graph/estimate/total/compare/result", response_class=HTMLResponse)
async def graph_estimate_total_compare_result(request: Request, term: str = Form(...)):
    csv_path = os.path.join("data", "一般工事売上データ.csv")

    # CSV読み込み
    try:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp932")
    except Exception as e:
        return HTMLResponse(content=f"<h3>CSV読み込みエラー: {e}</h3>", status_code=500)

    # 日付変換と期間設定
    df["作成日"] = pd.to_datetime(df["作成日"], errors="coerce")
    df["決定日"] = pd.to_datetime(df["決定日"], errors="coerce")

    y1 = int(term[:4])
    start = pd.Timestamp(f"{y1}-05-01")
    end = pd.Timestamp(f"{y1 + 1}-04-30")

    # 担当者一覧
    if "担当者名" not in df.columns:
        return HTMLResponse(content="<h3>CSVに担当者名列が存在しません</h3>", status_code=500)
    persons = sorted([p for p in df["担当者名"].dropna().unique() if "削除済み" not in p])

    # ▼ 見積集計（作成日）
    df_est = df[(df["作成日"] >= start) & (df["作成日"] <= end)].copy()
    df_est = df_est.sort_values("作成日").drop_duplicates("工事見積No.", keep="last")
    est_summary = df_est.groupby("担当者名").agg(
        見積金額合計=("小計", "sum"),
        見積件数=("工事見積No.", "count")
    ).reindex(persons, fill_value=0)

    # ▼ 決定集計（決定日）
    df_dec = df[(df["決定日"].notna()) & (df["決定日"] >= start) & (df["決定日"] <= end)].copy()
    df_dec = df_dec.sort_values("決定日").drop_duplicates("工事見積No.", keep="last")
    dec_summary = df_dec.groupby("担当者名").agg(
        決定金額合計=("小計", "sum"),
        決定件数=("工事見積No.", "count")
    ).reindex(persons, fill_value=0)

    # ▼ グラフ用データ
    estimate_amounts = est_summary["見積金額合計"].astype(int).tolist()
    estimate_counts = est_summary["見積件数"].astype(int).tolist()
    decision_amounts = dec_summary["決定金額合計"].astype(int).tolist()
    decision_counts = dec_summary["決定件数"].astype(int).tolist()

    # ▼ 全体集計
    estimate_total_raw = sum(estimate_amounts)
    decision_total_raw = sum(decision_amounts)
    total_estimate_count = sum(estimate_counts)
    total_decision_count = sum(decision_counts)
    estimate_per_case_raw = estimate_total_raw // total_estimate_count if total_estimate_count > 0 else 0

    estimate_total = f"{estimate_total_raw:,}"
    decision_total = f"{decision_total_raw:,}"
    estimate_per_case = f"{estimate_per_case_raw:,}"
    money_decision_rate = f"{(decision_total_raw / estimate_total_raw * 100):.1f}%" if estimate_total_raw > 0 else "0%"
    count_decision_rate = f"{(total_decision_count / total_estimate_count * 100):.1f}%" if total_estimate_count > 0 else "0%"

    return templates.TemplateResponse("graph_estimate_total_compare_result.html", {
        "request": request,
        "term": term,
        "persons": persons,
        "estimate_amounts": estimate_amounts,
        "estimate_counts": estimate_counts,
        "decision_amounts": decision_amounts,
        "decision_counts": decision_counts,
        "estimate_total": estimate_total,
        "decision_total": decision_total,
        "estimate_per_case": estimate_per_case,
        "money_decision_rate": money_decision_rate,
        "count_decision_rate": count_decision_rate
    })


@app.get("/graph/menu", response_class=HTMLResponse)
async def graph_menu(request: Request):
    today = datetime.today()
    year = today.year
    month = today.month - 1
    if month == 0:
        month = 12
        year -= 1
    default_params = {
        "year": year,
        "month": month,
        "work_types": ["点検及び検査"]
    }
    return templates.TemplateResponse("graph_menu.html", {
        "request": request,
        "default_params": default_params
    })


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
            "作業項目(箇所)": "項目",
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
            "作業項目(箇所)": "項目",
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
            "作業項目(箇所)": "項目",
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

# ==========================
#       API連携
# ==========================
@app.post("/api/receive_data")
async def receive_data(records: UploadFile = File(...)):
    contents = await records.read()

    # CSV読み込み
    try:
        new_df = pd.read_csv(io.BytesIO(contents), encoding="utf-8-sig")
    except UnicodeDecodeError:
        new_df = pd.read_csv(io.BytesIO(contents), encoding="cp932")

    # カラム名正規化（全角カッコ→半角）
    new_df.columns = [col.strip().replace("（", "(").replace("）", ")").replace('"', "").replace("'", "") for col in new_df.columns]

    print("📋 修正後カラム:", new_df.columns.tolist())

    # 作業時間処理
    time_col = next((col for col in new_df.columns if "作業時間" in col), None)
    new_df["作業時間"] = pd.to_numeric(new_df[time_col], errors="coerce") if time_col else 0.0

    expected_cols = ["作業ID", "作業日", "作業実施者", "作業項目(箇所)", "作業時間"]
    new_df = new_df[[col for col in new_df.columns if col in expected_cols]]
    new_df = new_df.reindex(columns=expected_cols)

    os.makedirs("data", exist_ok=True)
    save_path = os.path.join("data", "検査工数データ.csv")

    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        try:
            existing_df = pd.read_csv(save_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            existing_df = pd.read_csv(save_path, encoding="cp932")
    else:
        existing_df = pd.DataFrame(columns=expected_cols)

    existing_df.columns = [col.strip().replace("（", "(").replace("）", ")") for col in existing_df.columns]
    existing_df = existing_df[[col for col in existing_df.columns if col in expected_cols]]
    existing_df = existing_df.reindex(columns=expected_cols)

    # 重複排除した上で MultiIndex を作成
    key_cols = ["作業ID", "作業項目(箇所)"]
    new_df = new_df.drop_duplicates(subset=key_cols, keep="last")
    existing_df = existing_df.drop_duplicates(subset=key_cols, keep="last")

    try:
        new_df.set_index(key_cols, inplace=True)
        existing_df.set_index(key_cols, inplace=True)
    except KeyError:
        return JSONResponse(status_code=400, content={"status": "error", "message": "必要なキー列が存在しません。"})

    # 更新処理：新規追加 + 内容更新
    updated_df = existing_df.combine_first(new_df)
    updated_df.update(new_df)

    # 保存とGitHub反映
    updated_df.reset_index(inplace=True)
    updated_df.to_csv(save_path, index=False, encoding="utf-8-sig")

    try:
        GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        repo_owner = "otameshi-web"
        repo_name = "kousu-app"
        branch = "master"
        file_path = "data/検査工数データ.csv"
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
        get_resp = requests.get(api_url, headers=headers, params={"ref": branch})
        sha = get_resp.json().get("sha", None)

        with open(save_path, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode("utf-8")

        commit_message = f"自動更新: 検査工数データ ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
        data = {
            "message": commit_message,
            "content": encoded_content,
            "branch": branch
        }
        if sha:
            data["sha"] = sha

        put_resp = requests.put(api_url, headers=headers, json=data)

        if put_resp.status_code in [200, 201]:
            return JSONResponse(content={
                "status": "success",
                "message": f"{len(new_df)} 件のレコードを更新・追加して保存しました"
            })
        else:
            return JSONResponse(content={
                "status": "partial_success",
                "message": f"保存成功・GitHub反映失敗: {put_resp.json()}"
            }, status_code=500)

    except Exception as e:
        return JSONResponse(content={
            "status": "error",
            "message": f"保存成功・GitHub連携失敗: {str(e)}"
        }, status_code=500)

@app.post("/api/receive_kousu_data")
async def receive_kousu_data(records: UploadFile = File(...)):
    contents = await records.read()

    # CSV読み込み
    try:
        new_df = pd.read_csv(io.BytesIO(contents), encoding="utf-8-sig")
    except UnicodeDecodeError:
        new_df = pd.read_csv(io.BytesIO(contents), encoding="cp932")

    # ✅ カラム名の前後スペース削除＋全角カッコ→半角へ正規化
    new_df.columns = [col.strip().replace("（", "(").replace("）", ")").replace('"', "").replace("'", "") for col in new_df.columns]
    print("📋 修正後カラム:", new_df.columns.tolist())

    # ✅ 作業時間列の処理（「作業時間」や「作業時間(m)」に対応）
    time_col = next((col for col in new_df.columns if "作業時間" in col), None)
    if time_col:
        new_df["作業時間"] = pd.to_numeric(new_df[time_col], errors="coerce")
    else:
        new_df["作業時間"] = 0.0

    # ✅ 期待カラムを抽出・整形
    expected_cols = ["作業ID", "作業日", "作業実施者", "作業種別", "作業時間"]
    new_df = new_df[[col for col in new_df.columns if col in expected_cols]]
    new_df = new_df.reindex(columns=expected_cols)

    # ✅ 保存先のCSVを読み込み（なければ空のDataFrameを用意）
    os.makedirs("data", exist_ok=True)
    save_path = os.path.join("data", "工数データ.csv")
    # ファイルが存在し、サイズが0でないことを確認してから読み込む
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        try:
            existing_df = pd.read_csv(save_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                existing_df = pd.read_csv(save_path, encoding="cp932")
            except Exception:
                existing_df = pd.DataFrame(columns=expected_cols)
    else:
        existing_df = pd.DataFrame(columns=expected_cols)


    # ✅ 確実に必要列だけにし、indexを作業IDに設定
    existing_df.columns = [col.strip().replace("（", "(").replace("）", ")") for col in existing_df.columns]
    existing_df = existing_df[[col for col in existing_df.columns if col in expected_cols]]
    existing_df = existing_df.reindex(columns=expected_cols)

    try:
        existing_df.set_index("作業ID", inplace=True)
        new_df.set_index("作業ID", inplace=True)
    except KeyError:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "作業ID列が見つかりません。CSV列名をご確認ください。"}
        )

    # ✅ 上書き＋追加処理
    updated_df = existing_df.combine_first(new_df)
    updated_df.update(new_df)

    # ✅ 保存・GitHubへPush
    updated_df.reset_index(inplace=True)
    updated_df.to_csv(save_path, index=False, encoding="utf-8-sig")

    # ✅ GitHub連携
    try:
        GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        repo_owner = "otameshi-web"
        repo_name = "kousu-app"
        branch = "master"
        file_path = "data/工数データ.csv"
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }

        get_resp = requests.get(api_url, headers=headers, params={"ref": branch})
        sha = get_resp.json().get("sha", None)

        with open(save_path, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode("utf-8")

        commit_message = f"自動更新: 工数データ ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
        data = {
            "message": commit_message,
            "content": encoded_content,
            "branch": branch
        }
        if sha:
            data["sha"] = sha

        put_resp = requests.put(api_url, headers=headers, json=data)

        if put_resp.status_code in [200, 201]:
            return JSONResponse(content={
                "status": "success",
                "message": f"{len(new_df)} 件の新規・更新レコードを保存し、GitHub に反映しました"
            })
        else:
            return JSONResponse(content={
                "status": "partial_success",
                "message": f"保存成功・GitHub反映失敗: {put_resp.json()}"
            }, status_code=500)

    except Exception as e:
        return JSONResponse(content={
            "status": "error",
            "message": f"保存成功・GitHub連携失敗: {str(e)}"
        }, status_code=500)

@app.post("/api/receive_general_construction")
async def receive_general_construction(records: UploadFile = File(...)):
    contents = await records.read()

    # CSVの読み込み
    try:
        new_df = pd.read_csv(io.BytesIO(contents), encoding="utf-8-sig")
    except UnicodeDecodeError:
        new_df = pd.read_csv(io.BytesIO(contents), encoding="cp932")

    # カラム正規化
    new_df.columns = [col.strip().replace("（", "(").replace("）", ")").replace('"', "").replace("'", "") for col in new_df.columns]

    # 保存対象カラムと順番
    expected_cols = ["工事見積No.", "明細キー", "作成日", "決定日", "宛名", "建物名", "担当者名", "詳細", "小計", "消費税", "合計", "原価小計", "原価率", "利益率", "管理番号"]
    new_df = new_df[[col for col in new_df.columns if col in expected_cols]]
    new_df = new_df.reindex(columns=expected_cols)

    # 保存先のCSV読み込み
    os.makedirs("data", exist_ok=True)
    save_path = os.path.join("data", "一般工事売上データ.csv")

    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        try:
            existing_df = pd.read_csv(save_path, encoding="utf-8-sig")
        except:
            existing_df = pd.DataFrame(columns=expected_cols)
    else:
        existing_df = pd.DataFrame(columns=expected_cols)

    existing_df = existing_df[[col for col in existing_df.columns if col in expected_cols]]
    existing_df = existing_df.reindex(columns=expected_cols)

    try:
        existing_df.set_index(["工事見積No.", "明細キー"], inplace=True)
        new_df.set_index(["工事見積No.", "明細キー"], inplace=True)
    except KeyError:
        return JSONResponse(status_code=400, content={"status": "error", "message": "キー列が存在しません。"})

    # 更新・追加のみ（削除なし）
    updated_df = existing_df.combine_first(new_df)
    updated_df.update(new_df)

    updated_df.reset_index(inplace=True)
    updated_df.to_csv(save_path, index=False, encoding="utf-8-sig")

    # GitHubへ反映
    try:
        GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        repo_owner = "otameshi-web"
        repo_name = "kousu-app"
        branch = "master"
        file_path = "data/一般工事売上データ.csv"
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }

        get_resp = requests.get(api_url, headers=headers, params={"ref": branch})
        sha = get_resp.json().get("sha", None)

        with open(save_path, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode("utf-8")

        commit_message = f"自動更新: 一般工事売上データ ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
        data = {
            "message": commit_message,
            "content": encoded_content,
            "branch": branch
        }
        if sha:
            data["sha"] = sha

        put_resp = requests.put(api_url, headers=headers, json=data)

        if put_resp.status_code in [200, 201]:
            return JSONResponse(content={"status": "success", "message": f"{len(new_df)} 件を保存・GitHubに反映しました"})
        else:
            return JSONResponse(content={"status": "partial_success", "message": f"保存成功・GitHub反映失敗: {put_resp.json()}"}, status_code=500)

    except Exception as e:
        return JSONResponse(content={"status": "error", "message": f"保存成功・GitHub連携失敗: {str(e)}"}, status_code=500)


# ==========================
#    renderをGitHubから起動
# ==========================
@app.get("/healthcheck")
def healthcheck():
    return JSONResponse(content={"status": "ok", "message": "healthcheck successful"})

