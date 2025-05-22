import logging

logging.basicConfig(
    filename="auto_update.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def logprint(message):
    print(message)
    logging.info(message)


import subprocess
import sys
import os

# スクリプトのある場所に移動
os.chdir(r"C:\Users\日本エレベーター管理株式会社\Desktop\kousu_app")

# ① download_csv.py を実行
logprint("▶ download_csv.py 実行中...")
subprocess.run([sys.executable, "download_csv.py"], check=True, capture_output=True, text=True)

# ② update_csv.py を実行
logprint("▶ update_csv.py 実行中...")
subprocess.run([sys.executable, "update_csv.py"], check=True, capture_output=True, text=True)

# ③ Git操作
logprint("▶ GitHub に push...")
subprocess.run(["git", "add", "data/工数データ.csv"], check=True, capture_output=True, text=True)
subprocess.run(["git", "commit", "-m", "自動更新"], check=True, capture_output=True, text=True)
subprocess.run(["git", "push", "origin", "master"], check=True, capture_output=True, text=True)

logprint("✅ すべての処理が完了しました")
