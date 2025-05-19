import os
import time
import subprocess
import tempfile
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# .env読み込み
load_dotenv()
LOGIN_ID = os.getenv("RAKURAKU_ID")
LOGIN_PASSWORD = os.getenv("RAKURAKU_PASSWORD")

# 各種パス
driver_path = r"C:\Users\日本エレベーター管理株式会社\Documents\楽々販売用Python\msedgedriver.exe"
ahk_path = r"C:\Users\日本エレベーター管理株式会社\Desktop\kousu_app\cert_select.ahk"
download_dir = os.path.join(os.environ["USERPROFILE"], "Downloads")

# Edge設定
user_data_dir = tempfile.mkdtemp()
options = Options()
options.use_chromium = True
options.add_argument(f"--user-data-dir={user_data_dir}")
prefs = {"download.default_directory": download_dir}
options.add_experimental_option("prefs", prefs)

# Edge起動
service = Service(executable_path=driver_path)
driver = webdriver.Edge(service=service, options=options)

# AutoHotkeyで証明書選択
subprocess.Popen([r"C:\Program Files\AutoHotkey\v2\AutoHotkey.exe", ahk_path])

# 楽々販売へアクセス
driver.get("https://hnsslngqdn00197.rakurakuhanbai.jp/tr4pzta")

try:
    # ログイン
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "loginId")))
    driver.find_element(By.ID, "loginId").send_keys(LOGIN_ID)
    driver.find_element(By.ID, "loginPassword").send_keys(LOGIN_PASSWORD)
    driver.find_element(By.ID, "jq-loginSubmit").click()
    WebDriverWait(driver, 10).until(EC.url_changes("https://hnsslngqdn00197.rakurakuhanbai.jp/tr4pzta"))
    print(" ログイン成功")

    # iframe切替とクリック操作
    driver.switch_to.default_content()
    driver.switch_to.frame("side")
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "nav-dbg-100143"))).click()
    print(" 工務管理をクリックしました")
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "nav-db-101217"))).click()
    print(" 作業履歴をクリックしました")
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "menuli_102577"))).click()
    print(" 工数データをクリックしました")

    driver.switch_to.default_content()
    driver.switch_to.frame("main")
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "link_menu_box"))).click()
    print(" 三本線メニューをクリックしました")

    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "popupCsvExport"))).click()
    print(" CSV出力ボタンをクリックしました")

    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "csv_confirm_start"))).click()
    print(" ダウンロードボタンをクリックしました（CSV生成開始）")

    #  CSV生成完了ポップアップのリンクをクリック（30秒猶予）
    driver.switch_to.default_content()
    driver.switch_to.frame("main")
    download_link = WebDriverWait(driver, 30).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#csv_complete_link a"))
    )
    print(f" リンク表示成功: {download_link.text}")

    # 通常クリックでだめならJSでクリック
    try:
        download_link.click()
    except:
        driver.execute_script("arguments[0].click();", download_link)
    print(" ダウンロードリンクをクリックしました")

    # ダウンロード完了待ち
    time.sleep(5)

    # 最新CSVを確認
    csv_files = [f for f in os.listdir(download_dir) if f.startswith("作業履歴：工数データ") and f.endswith(".csv")]
    if csv_files:
        latest = max([os.path.join(download_dir, f) for f in csv_files], key=os.path.getmtime)
        print(f" ダウンロード完了: {latest}")
    else:
        print(" ダウンロードフォルダにCSVが見つかりません")

except Exception as e:
    print(" エラー:", e)

finally:
    pass
    # driver.quit()  # 自動で閉じたい場合はコメントアウト解除
