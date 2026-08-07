# lib/dashscope_text.py — 文本模型封装（apiKey 参数化，无降级）
# 模型：qwen3.7-plus（OpenAI 兼容接口）

import json
from pathlib import Path
from typing import List, Dict, Optional

import requests

from config import (
    DASHSCOPE_TEXT_BASE_URL,
    TEXT_MODEL,
    TEXT_TIMEOUT,
    TEXT_TEMPERATURE,
    TEXT_MAX_TOKENS,
)
from lib.errors import DashScopeError, parse_dashscope_error, create_timeout_error

# ===== 数据加载 =====
_DATA_DIR = Path(__file__).parent.parent / "data"


def _load_json(filename: str) -> dict:
    with open(_DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


_QUESTIONS = _load_json("questions.json")
_PSYCH_CORPUS = _load_json("psych-corpus.json")


# ===== 核心调用 =====


def generate_text(
    api_key: str,
    messages: List[Dict[str, str]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """
    调用文本模型生成内容
    :param api_key: 用户提供的百炼 API Key
    :param messages: 消息数组 [{role, content}, ...]
    :param temperature: 温度参数
    :param max_tokens: 最大 token 数
    :returns: 模型生成的文本
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
            f"{DASHSCOPE_TEXT_BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": TEXT_MODEL,
                "messages": messages,
                "temperature": temperature if temperature is not None else TEXT_TEMPERATURE,
                "max_tokens": max_tokens if max_tokens is not None else TEXT_MAX_TOKENS,
                "stream": False,
                "enable_thinking": False,
            },
            timeout=TEXT_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise create_timeout_error("文本生成")
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
    content = data.get("choices", [{}])[0].get("message", {}).get("content")

    if not content:
        raise DashScopeError(
            "TEXT_GEN_FAILED",
            "文本模型返回内容为空，请重试",
            500,
        )

    return content


# ===== Skill A：生成像素画提示词 =====


def _build_skill_a_system_prompt() -> str:
    return """你是一位像素艺术提示词专家。根据用户的问卷选择，生成一段精确的英文像素画提示词。

要求：
1. 提示词必须以 "pixel art, " 开头
2. 包含以下要素：光线、场景、人物/主体、道具、氛围、构图
3. 强调像素风特征：clean pixel edges, limited 16-color palette, no anti-aliasing
4. 提示词长度控制在 80-150 个英文单词
5. 不要包含任何解释性文字，只输出提示词本身
6. 结尾加上 "pixel art style, retro game aesthetic" """


def _build_skill_a_user_prompt(answers: Dict[str, str], world_name: str) -> str:
    questions = _QUESTIONS["questions"]

    def find_opt(q_idx: int, ans: str) -> dict:
        opts = questions[q_idx]["options"]
        for o in opts:
            if o["id"] == ans:
                return o
        return {}

    q1 = find_opt(0, answers.get("Q1", ""))
    q2 = find_opt(1, answers.get("Q2", ""))
    q3 = find_opt(2, answers.get("Q3", ""))
    q4 = find_opt(3, answers.get("Q4", ""))
    q5 = find_opt(4, answers.get("Q5", ""))
    q6 = find_opt(5, answers.get("Q6", ""))

    return f"""世界名称：{world_name}

光线：{q1.get("visual", "")}
场景：{q2.get("visual", "")}
道具：{q3.get("visual", "")}
同伴：{q4.get("visual", "")}
困境/状态：{q5.get("visual", "")}
构图提示：{q6.get("compose_hint", "")}

请根据以上信息生成像素画提示词。"""


def generate_prompt(api_key: str, answers: Dict[str, str], world_name: str) -> str:
    """Skill A：生成像素画英文提示词"""
    system_prompt = _build_skill_a_system_prompt()
    user_prompt = _build_skill_a_user_prompt(answers, world_name)

    return generate_text(
        api_key,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )


# ===== Skill B：生成心理报告 =====


def _build_skill_b_system_prompt(answers: Dict[str, str]) -> str:
    corpus = _PSYCH_CORPUS["corpus"]
    questions = _QUESTIONS["questions"]

    # 只提取用户选择的 5 个心理标签对应的语料，减少 prompt 长度
    relevant_tags = []
    for i in range(5):
        q = questions[i]
        key = f"Q{i + 1}"
        ans = answers.get(key, "")
        for o in q.get("options", []):
            if o["id"] == ans and o.get("psych"):
                relevant_tags.append(o["psych"])

    corpus_text = ""
    for tag in relevant_tags:
        if tag in corpus:
            entries = corpus[tag]
            numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(entries))
            corpus_text += f"\n【{tag}】\n{numbered}\n"

    return f"""你是一位温暖的心理洞察师，擅长用诗意的语言解读人的内心世界。根据用户的问卷选择，生成一段心灵映照报告。

报告格式要求：
1. 以世界名称作为标题
2. 分 3-4 个自然段，每段聚焦一个心理主题
3. 每段以温暖、接纳的语气书写，不评判、不说教
4. 最后以"像素箴言"结尾——一句简短的、像游戏台词一样的格言
5. 全文使用中文，字数 300-500 字

心理标签语料库（参考但不限于）：
{corpus_text}

注意：不要直接复制语料，要结合用户的具体选择进行个性化解读。"""


def _build_skill_b_user_prompt(answers: Dict[str, str], world_name: str) -> str:
    questions = _QUESTIONS["questions"]

    selections = []
    for i in range(5):
        q = questions[i]
        key = f"Q{i + 1}"
        ans = answers.get(key, "")
        for o in q.get("options", []):
            if o["id"] == ans:
                selections.append(
                    f"{q['title']}\n  选择：{o['text']}\n  心理标签：{o.get('psych', '')}"
                )
                break

    q6_opt = {}
    for o in questions[5].get("options", []):
        if o["id"] == answers.get("Q6", ""):
            q6_opt = o
            break

    return f"""世界名称：{world_name}

用户的选择：
{chr(10).join(selections)}

世界形状：{q6_opt.get("text", "")}

请根据以上选择生成心灵映照报告。"""


def generate_report(api_key: str, answers: Dict[str, str], world_name: str) -> str:
    """Skill B：生成心灵映照报告"""
    system_prompt = _build_skill_b_system_prompt(answers)
    user_prompt = _build_skill_b_user_prompt(answers, world_name)

    return generate_text(
        api_key,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
