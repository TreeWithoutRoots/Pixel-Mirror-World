# lib/storage.py — 图片存储（Supabase 可选，未配置时使用本地存储）

import os
import time
import random
import string
from pathlib import Path
from typing import Optional, List, Dict

import requests
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv(Path(__file__).parent.parent / ".env")

from config import SUPABASE_BUCKET_NAME

# ===== 环境变量检查 =====

def _get_supabase_config() -> Optional[Dict[str, str]]:
    """检查 Supabase 环境变量是否配置"""
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if url and key:
        return {"url": url, "key": key}
    return None


def is_supabase_configured() -> bool:
    """检查 Supabase 是否已配置"""
    return _get_supabase_config() is not None


# ===== 本地存储 =====

_LOCAL_DIR = Path(__file__).parent.parent / "uploads"
_LOCAL_DIR.mkdir(exist_ok=True)


def _save_local(image_bytes: bytes) -> str:
    """保存图片到本地 uploads 目录"""
    name = f"raw/{int(time.time() * 1000)}-{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}.png"
    file_path = _LOCAL_DIR / name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    return str(file_path)


# ===== Supabase 上传 =====

def upload_image(image_bytes: bytes) -> str:
    """
    上传图片并返回可访问的 URL 或路径
    - Supabase 已配置：上传到 Storage 并返回公共 URL
    - Supabase 未配置：保存到本地 uploads 目录并返回路径
    """
    config = _get_supabase_config()
    if not config:
        return _save_local(image_bytes)

    try:
        name = f"raw/{int(time.time() * 1000)}-{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}.png"
        url = f"{config['url']}/storage/v1/object/{SUPABASE_BUCKET_NAME}/{name}"

        resp = requests.post(
            url,
            headers={
                "apikey": config["key"],
                "Authorization": f"Bearer {config['key']}",
                "Content-Type": "image/png",
                "x-upsert": "false",
            },
            data=image_bytes,
            timeout=30,
        )

        if not resp.ok:
            raise Exception(f"Supabase 上传失败: HTTP {resp.status_code}")

        # 构建公共 URL
        public_url = f"{config['url']}/storage/v1/object/public/{SUPABASE_BUCKET_NAME}/{name}"
        return public_url

    except Exception as e:
        # Supabase 上传失败时回退到本地存储
        print(f"[storage] Supabase 上传失败，回退到本地存储: {e}")
        return _save_local(image_bytes)


# ===== 数据库操作（可选）=====

def save_submission(data: Dict) -> Optional[str]:
    """
    将生成结果保存到 Supabase submissions 表
    如果 Supabase 未配置，返回 None
    """
    config = _get_supabase_config()
    if not config:
        return None

    try:
        resp = requests.post(
            f"{config['url']}/rest/v1/submissions",
            headers={
                "apikey": config["key"],
                "Authorization": f"Bearer {config['key']}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=data,
            timeout=15,
        )

        if not resp.ok:
            print(f"[storage] 数据库写入失败: HTTP {resp.status_code}")
            return None

        result = resp.json()
        if isinstance(result, list) and len(result) > 0:
            return result[0].get("id")
        return None

    except Exception as e:
        print(f"[storage] 数据库写入异常: {e}")
        return None


def get_submissions(limit: int = 20) -> List[Dict]:
    """
    从 Supabase 获取历史记录
    如果 Supabase 未配置，返回空列表
    """
    config = _get_supabase_config()
    if not config:
        return []

    try:
        resp = requests.get(
            f"{config['url']}/rest/v1/submissions?select=id,world_name,image_url,image_shape,created_at&order=created_at.desc&limit={limit}",
            headers={
                "apikey": config["key"],
                "Authorization": f"Bearer {config['key']}",
            },
            timeout=15,
        )

        if not resp.ok:
            return []

        return resp.json()

    except Exception as e:
        print(f"[storage] 获取历史记录失败: {e}")
        return []
