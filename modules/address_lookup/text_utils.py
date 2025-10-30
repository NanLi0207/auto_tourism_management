"""
text_utils.py
========================
用于对地点关键词进行标准化、停用词过滤和相似度计算。
支持：
- 关键词清洗
- Token 分词
- Jaccard 相似度
- 编辑距离相似度

这些方法常用于判断数据库中是否已存在相似地址，减少重复抓取。
"""

import re
from difflib import SequenceMatcher
from .config import STOPWORDS_BASE, CITY_FOR_QUERY_EN


def stopwords():
    """
    获取停用词列表
    ------------------------
    返回：
        set[str]，包含停用词和城市名
    """
    sw = set(STOPWORDS_BASE)
    if CITY_FOR_QUERY_EN:
        sw.add(CITY_FOR_QUERY_EN.lower())
    return sw


def normalize_keyword(s: str) -> str:
    """
    对关键词进行标准化
    ------------------------
    - 转小写
    - 去除特殊符号
    - 去除多余空格

    Args:
        s (str): 原始关键词

    Returns:
        str: 处理后的标准化字符串
    """
    s = (s or "").lower().strip()
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def token_set(s: str):
    """
    分词 + 停用词过滤
    ------------------------
    Args:
        s (str): 原始字符串

    Returns:
        list[str]: 处理后的 token 列表
    """
    tokens = normalize_keyword(s).split()
    sw = stopwords()
    seen, out = set(), []
    for t in tokens:
        if t in sw:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def jaccard(a: list, b: list) -> float:
    """
    Jaccard 相似度计算
    ------------------------
    相似度 = 交集元素数 / 并集元素数

    Args:
        a (list): token 列表
        b (list): token 列表

    Returns:
        float: 相似度（0~1）
    """
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def edit_sim(a: str, b: str) -> float:
    """
    编辑距离相似度计算（SequenceMatcher）
    ------------------------
    适合处理轻微拼写错误的情况。

    Args:
        a (str): 字符串 A
        b (str): 字符串 B

    Returns:
        float: 相似度（0~1）
    """
    a2 = " ".join(token_set(a))
    b2 = " ".join(token_set(b))
    return SequenceMatcher(None, a2, b2).ratio()
