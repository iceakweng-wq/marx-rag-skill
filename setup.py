"""
马恩全集 RAG Skill — 安装脚本

从项目仓库下载预构建的向量数据库，或从本地构建。
"""

import os
import sys
import zipfile
import urllib.request
import hashlib
import shutil
from pathlib import Path

SKILL_ROOT = Path(__file__).parent
CHROMA_DIR = SKILL_ROOT / "chroma_db"

# 数据库下载地址（发布 release 后更新此 URL）
# 格式：release 时上传 chroma_db.zip，使用者运行 setup.py 自动下载
DB_URL = ""  # TODO: 发布 release 后填写


def download_database():
    """从 release 下载预构建数据库。"""
    if not DB_URL:
        print("=" * 50)
        print("  方式一：使用主项目的构建脚本")
        print("=" * 50)
        print()
        print("  如果你有完整项目，可以直接复制数据库：")
        print("  xcopy /E ..\\marx-rag\\chroma_db chroma_db\\")
        print()
        print("=" * 50)
        print("  方式二：从主项目构建")
        print("=" * 50)
        print()
        print("  cd ../marx-rag")
        print("  python scripts/02_chunk.py")
        print("  python scripts/03_embed.py")
        print("  xcopy /E chroma_db ..\\marx-rag-skill\\chroma_db\\")
        print()
        return

    print(f"正在下载数据库 (约 800MB)...")
    zip_path = SKILL_ROOT / "chroma_db.zip"
    try:
        urllib.request.urlretrieve(DB_URL, zip_path)
        print("解压中...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(SKILL_ROOT)
        zip_path.unlink()
        print("完成！")
    except Exception as e:
        print(f"下载失败: {e}")
        sys.exit(1)


def check_database():
    """检查数据库是否可用。"""
    sqlite_path = CHROMA_DIR / "chroma.sqlite3"
    if sqlite_path.exists():
        size_mb = sqlite_path.stat().st_size / 1024 / 1024
        print(f"数据库已就绪 ({size_mb:.0f} MB)")
        return True
    return False


if __name__ == "__main__":
    print("马恩全集 RAG Skill — 安装")
    print("=" * 50)

    if check_database():
        sys.exit(0)

    print("\n数据库文件较大 (~800MB)，未包含在 git 仓库中。\n")
    download_database()
