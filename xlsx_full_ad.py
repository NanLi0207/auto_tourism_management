# -*- coding: utf-8 -*-
import re
import sys
import pandas as pd

# === 直接从同目录导入你提供的模块 ===
from modules.google_maps_lookup import (
    init_db as gm_init_db,
    init_driver as gm_init_driver,
    quit_driver as gm_quit_driver,
    search_address as gm_search_address,
)

INPUT_FILE = "a251016.xlsx"
OUTPUT_FILE = "a251016_full_ad.xlsx"


# ---- 帮助函数：找到并补全 L 行 ----
def enrich_note_L_line(note_text: str) -> str:
    """
    仅修改 note 中的 L: 行：
      - 若 L 行为空：不变
      - 若 L 行有内容：调用 search_address(query, db_kind="pickup") 补全地址，并在原内容后追加 ' — 地址'
    其他行保持不变；不跨行解析；支持英文/中文冒号。
    """
    if not isinstance(note_text, str):
        return note_text

    lines = note_text.splitlines()
    changed = False

    for i, raw in enumerate(lines):
        # 匹配 'L:' 或 'L：'（允许前后空格），捕获前缀(L:)与内容
        m = re.match(r"^(\s*[Ll]\s*[:：]\s*)(.*)\s*$", raw)
        if not m:
            continue

        prefix = m.group(1)  # 如 "L: "（含原有空格）
        current_val = (m.group(2) or "").strip()

        # L 为空 -> 不动
        if current_val == "":
            continue

        # 若已经有 ', ' 补全过，可以跳过（避免重复追加）
        if ", " in current_val:
            continue

        # 调用你的地址补全（使用 pickup 库）
        try:
            result = gm_search_address(current_val, db_kind="pickup")
            full_addr = (result or {}).get("address", "").strip()
        except Exception as e:
            print(f"⚠️ 补全失败（L='{current_val}'）：{e}")
            full_addr = ""

        if full_addr:
            # 仅改 L 行：原值 + ' — ' + 标准地址
            lines[i] = f"{prefix}{current_val}, {full_addr}"
            changed = True
        else:
            # 未找到就保持原样
            pass

        # 只处理第一条 L 行（通常一条 note 只有一行 L）
        break

    return "\n".join(lines) if changed else note_text


def main(input_file=INPUT_FILE, output_file=OUTPUT_FILE):
    # 1) 初始化 DB 与 Driver（按你的模块约定）
    gm_init_db("pickup")  # 只需补全 L（meeting point），用 pickup 库
    gm_init_driver()  # 显式启动浏览器会话

    try:
        # 2) 读取 Excel
        df = pd.read_excel(input_file)

        # 3) 必要列检查
        required_cols = {"note"}
        missing = required_cols - set(df.columns.str.lower())
        # 兼容大小写：重命名成统一小写列
        df.columns = [c.lower() for c in df.columns]
        if "note" not in df.columns:
            raise ValueError("输入表中缺少列: 'note'")

        # 4) 逐行处理 note，只补 L 行
        for idx, row in df.iterrows():
            original_note = row["note"]
            new_note = enrich_note_L_line(original_note)
            if new_note != original_note:
                print(f"✅ 第 {idx + 2} 行 L 已补全")
            df.at[idx, "note"] = new_note

        # 5) 写回新表
        df.to_excel(output_file, index=False)
        print(f"\n🎉 已生成：{output_file}")

    finally:
        # 6) 关闭浏览器
        gm_quit_driver()


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        INPUT_FILE = sys.argv[1]
    if len(sys.argv) >= 3:
        OUTPUT_FILE = sys.argv[2]
    main(INPUT_FILE, OUTPUT_FILE)
