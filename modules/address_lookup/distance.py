"""
distance.py
========================
提供计算两个地理坐标点之间距离的工具函数。

使用 Haversine 公式计算球面距离（单位：米）
"""

import math


def haversine_m(lat1, lon1, lat2, lon2):
    """
    Haversine 公式计算两个经纬度之间的距离（米）
    ------------------------
    Args:
        lat1 (float): 起点纬度
        lon1 (float): 起点经度
        lat2 (float): 终点纬度
        lon2 (float): 终点经度

    Returns:
        float: 距离（单位：米），如果输入不合法返回 None
    """
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
    except Exception:
        return None

    # 地球半径（米）
    R = 6371000

    # 转换为弧度
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    # Haversine 公式
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
