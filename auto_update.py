import subprocess
import sys
import os

# スクリプトのある場所に移動
os.chdir(r"C:\Users\日本エレベーター管理株式会社\Desktop\kousu_app")

# ① download_csv.py を実行
print("▶ download_csv.py 実行中...")
subprocess.run([sys.executable, "download_csv.py"], check=True)

# ② update_csv.py を実行
print("▶ update_csv.py 実行中...")
subprocess.run([sys.executable, "update_csv.py"], check=True)

# ③ Git操作
print("▶ GitHub に push...")
subprocess.run(["git", "add", "data/工数データ.csv"], check=True)
subprocess.run(["git", "commit", "-m", "自動更新"], check=True)
subprocess.run(["git", "push", "origin", "master"], check=True)

print("✅ すべての処理が完了しました")
