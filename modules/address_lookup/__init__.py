"""
address_lookup 模块
========================
该模块用于通过 Google Maps 获取地理位置信息。
核心功能包括：
- 浏览器控制与搜索自动化（Selenium）
- 地址抓取与坐标解析
- 文本匹配与标准化
- 地理距离计算

外部调用时可以直接导入模块内的核心函数：
    from modules.address_lookup import search_place, haversine_m
"""

from .geocode import search_place
from .distance import haversine_m
