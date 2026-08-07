# lib/sensitive.py — 敏感词过滤

import json
from pathlib import Path
from typing import Tuple, List

_DATA_PATH = Path(__file__).parent.parent / "data" / "sensitive-words.json"


def _load_words() -> List[str]:
    """加载敏感词列表"""
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("words", [])


_WORDS = _load_words()


def filter_sensitive_words(text: str) -> Tuple[bool, List[str]]:
    """
    检查文本是否包含敏感词
    :returns: (是否包含敏感词, 匹配到的敏感词列表)
    """
    # 首尾补空格，确保能匹配位于文本开头/结尾的英文敏感词
    # （敏感词列表中英文词条带前导空格，用于避免子串误匹配如 "fucking" 匹配 "fuck"）
    padded_text = f" {text.lower()} "
    found = [w for w in _WORDS if w.lower() in padded_text]
    return len(found) > 0, found
