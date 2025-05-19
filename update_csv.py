import os
import shutil

# 📁 ダウンロードフォルダパス（Windows用）
downloads = os.path.join(os.environ["USERPROFILE"], "Downloads")
project_dir = os.path.dirname(__file__)
target_file = os.path.join(project_dir, "data", "工数データ.csv")

# 📄 ダウンロード済みの工数データCSVを探す
csv_files = [
    f for f in os.listdir(downloads)
    if f.startswith("作業履歴：工数データ") and f.endswith(".csv")
]

if not csv_files:
    print("❌ ダウンロードフォルダにCSVファイルが見つかりません。")
    exit()

# 📄 最も新しいファイルを選択
latest_file = max(
    [os.path.join(downloads, f) for f in csv_files],
    key=os.path.getmtime
)

# ⬇️ data/フォルダにコピーして上書き
shutil.copyfile(latest_file, target_file)
print(f"✅ コピー成功: {latest_file} → {target_file}")
