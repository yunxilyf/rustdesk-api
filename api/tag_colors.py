# -*- coding: utf-8 -*-
"""标签颜色工具。

RustDesk 客户端把标签颜色存成 Flutter ``Color.value``，即 32 位 ARGB 整数
（例如青色 0xFF00BCD4 = 4278238420）。控制台历史版本存的是调色板下标
(0..11)，客户端读出来会得到近透明的颜色，表现为标签没有圆点、选中时变白。

客户端调色板来自 ``flutter/lib/common.dart:1416 str2color2``，固定 12 色，
顺序为 red/green/blue/orange/purple/grey/cyan/lime/teal/pink[200]/indigo/brown。
本模块提供同一套调色板与归一化函数，保证两端颜色一致。
"""

TAG_COLORS = [
    (0xFFF44336, "红"),
    (0xFF4CAF50, "绿"),
    (0xFF2196F3, "蓝"),
    (0xFFFF9800, "橙"),
    (0xFF9C27B0, "紫"),
    (0xFF9E9E9E, "灰"),
    (0xFF00BCD4, "青"),
    (0xFFCDDC39, "柠檬"),
    (0xFF009688, "蓝绿"),
    (0xFFF48FB1, "粉"),
    (0xFF3F51B5, "靛蓝"),
    (0xFF795548, "棕"),
]

PALETTE = [c[0] for c in TAG_COLORS]


def normalize_color(value, name=""):
    """把任意来源的颜色统一成客户端可识别的 ARGB 整数。

    - 已经是 ARGB（>= 0x1000000）的原样保留；
    - 0..11 视为旧调色板下标，映射到对应 ARGB；
    - 其它值按标签名哈希挑一个调色板颜色（与客户端 str2color2 一致）。
    """
    try:
        color = int(value or 0)
    except (TypeError, ValueError):
        color = 0
    if color >= 0x1000000:
        return color & 0xFFFFFFFF
    if 0 <= color < len(PALETTE):
        return PALETTE[color]
    total = sum(ord(ch) for ch in (name or ""))
    return PALETTE[total % len(PALETTE)]
