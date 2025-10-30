"""
config.py
========================
用于集中管理与地址查找相关的所有配置参数，方便统一修改。
包含默认搜索位置、城市信息、文本匹配阈值、Selenium 配置等。
"""

import os

# ==================== 地理位置默认参数 ====================
# 默认地图打开的中心点坐标（阿姆斯特丹）
CITY_CENTER_LAT = 52.3728
CITY_CENTER_LNG = 4.8936
CITY_CENTER_ZOOM = 13  # 默认缩放级别

# 城市名称（用于自动补全搜索）
CITY_FOR_QUERY_EN = "Amsterdam"

# 是否在搜索关键词后自动加上城市名称
APPEND_CITY_TO_QUERY = True


# ==================== 浏览器配置 ====================
# Selenium 显式等待的短时和长时（秒）
SELENIUM_SHORT_WAIT = 4
SELENIUM_LONG_WAIT = 12

# 搜索间隔（用于防止 Google Maps 限速）
SEARCH_THROTTLE_SECONDS = 0.6


# ==================== 文本匹配相关 ====================
# Jaccard 相似度最低阈值
JACCARD_MIN = 0.80
# 编辑相似度最低阈值
EDIT_SIM_MIN = 0.92
# Top1 与 Top2 相似度的最小差距
TOP2_MARGIN_MIN = 0.05

# 文本匹配停用词（在匹配时会忽略这些词）
STOPWORDS_BASE = {
    "amsterdam",
    "hotel",
    "hotels",
    "the",
    "by",
    "hostel",
    "inn",
    "apartment",
    "apartments",
    "residence",
    "collection",
    "city",
    "center",
    "centre",
    "netherlands",
}
