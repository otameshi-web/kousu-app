import time
import os
import subprocess
import tempfile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

# .envファイルからログイン情報を読み込み
load_dotenv()
login_id = os.getenv("RAKURAKU_ID")
login_password = os.getenv("RAKURAKU_PASSWORD")

# 一時プロファイル作成（証明書ポップアップの発生を確実に）
user_data_dir = tempfile.mkdtemp()

# Edge設定
options = Options()
options.use_chromium = True
options.add_argument(f"--user-data-dir={user_data_dir}")

# ドライバ設定
driver_path = r"C:\Users\日本エレベーター管理株式会社\Documents\楽々販売用Python\msedgedriver.exe"
service = Service(executable_path=driver_path)

# ✅ AutoHotkeyスクリプトのパス（← ここを書き換えてください）
ahk_path = r"C:\Users\日本エレベーター管理株式会社\Desktop\kousu_app\cert_select.ahk"

# 🔄 証明書選択スクリプトを先に実行（非同期でバックグラウンド）
subprocess.Popen(["C:\\Program Files\\AutoHotkey\\v2\\AutoHotkey.exe", ahk_path])

# 🔓 Edge起動 → 証明書選択ページ表示
driver = webdriver.Edge(service=service, options=options)
driver.get("https://hnsslngqdn00197.rakurakuhanbai.jp/tr4pzta")

# 🔐 ログイン処理
try:
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "loginId")))
    driver.find_element(By.ID, "loginId").send_keys(login_id)
    driver.find_element(By.ID, "loginPassword").send_keys(login_password)
    driver.find_element(By.ID, "jq-loginSubmit").click()

    WebDriverWait(driver, 10).until(EC.url_changes("https://hnsslngqdn00197.rakurakuhanbai.jp/tr4pzta"))
    print("✅ ログイン成功")

except Exception as e:
    print("❌ ログイン失敗:", e)

# driver.quit()  # 自動で閉じたくない場合はコメントアウト
