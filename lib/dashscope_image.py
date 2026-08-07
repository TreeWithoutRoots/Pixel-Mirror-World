# lib/dashscope_image.py — 文生图封装（apiKey 参数化，无降级）
# 模型：wan2.6-t2i（通义万相同步调用）

import requests

from config import (
    DASHSCOPE_IMAGE_BASE_URL,
    IMAGE_MODEL,
    IMAGE_TIMEOUT,
    IMAGE_DOWNLOAD_TIMEOUT,
    NEGATIVE_PROMPT,
)
from lib.errors import DashScopeError, parse_dashscope_error, create_timeout_error


def generate_image(api_key: str, prompt: str, size: str) -> str:
    """
    调用万相 2.6 同步生成像素图
    :param api_key: 用户提供的百炼 API Key
    :param prompt: 文生图提示词（来自 Skill A）
    :param size: 尺寸，格式 "宽*高"（如 "1280*1280"）
    :returns: 临时图片 URL（24小时有效）
    :raises DashScopeError: 无降级，直接抛错
    """
    if not api_key:
        raise DashScopeError(
            "MISSING_API_KEY",
            "未提供 API Key，请返回输入页面填写",
            400,
        )

    try:
        response = requests.post(
            f"{DASHSCOPE_IMAGE_BASE_URL}/services/aigc/multimodal-generation/generation",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": IMAGE_MODEL,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"text": prompt}],
                        },
                    ],
                },
                "parameters": {
                    "size": size,
                    "n": 1,
                    "negative_prompt": NEGATIVE_PROMPT,
                    "prompt_extend": False,
                    "watermark": False,
                },
            },
            timeout=IMAGE_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise create_timeout_error("图像生成")
    except requests.exceptions.SSLError:
        raise DashScopeError(
            "SSL_ERROR",
            "SSL 连接失败，可能是 VPN/代理/防火墙拦截了 HTTPS 请求。"
            "请尝试关闭 VPN 或代理后重试",
            500,
        )
    except requests.exceptions.ConnectionError as e:
        raise DashScopeError(
            "NETWORK_ERROR",
            f"网络请求失败：{e}",
            500,
        )

    if not response.ok:
        try:
            error_body = response.json()
        except Exception:
            error_body = {}
        raise parse_dashscope_error(response.status_code, error_body)

    data = response.json()

    # 同步调用响应结构：output.choices[0].message.content[0].image
    image_url = (
        data.get("output", {})
        .get("choices", [{}])[0]
        .get("message", {})
        .get("content", [{}])[0]
        .get("image")
    )

    if not image_url:
        raise DashScopeError(
            "IMAGE_GEN_FAILED",
            "文生图返回结果为空，请重试",
            500,
        )

    return image_url


def download_image(url: str) -> bytes:
    """
    下载临时图片为 bytes（用于转存或本地显示）
    :param url: 临时图片 URL
    :returns: 图片二进制数据
    """
    try:
        response = requests.get(url, timeout=IMAGE_DOWNLOAD_TIMEOUT)
    except requests.exceptions.Timeout:
        raise create_timeout_error("图片下载")
    except requests.exceptions.SSLError:
        raise DashScopeError(
            "SSL_ERROR",
            "SSL 连接失败，可能是 VPN/代理/防火墙拦截了 HTTPS 请求。"
            "请尝试关闭 VPN 或代理后重试",
            500,
        )
    except requests.exceptions.ConnectionError as e:
        raise DashScopeError(
            "NETWORK_ERROR",
            f"图片下载网络请求失败：{e}",
            500,
        )

    if not response.ok:
        raise DashScopeError(
            "IMAGE_GEN_FAILED",
            f"图片下载失败：HTTP {response.status_code}",
            500,
        )

    return response.content
