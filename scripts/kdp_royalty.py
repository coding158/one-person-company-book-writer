#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KDP 到手金额与定价测算（纯标准库，无网络、无外联）。

规则来源：Amazon KDP 官方帮助页
  - eBook List Price Requirements（价带、配送费）
    https://kdp.amazon.com/en_US/help/topic/G200634560
    该页写明：2026-07-07 起 Amazon.com 的 70% 价带由 $2.99-$9.99 扩至 $2.99-$12.99。
  - KDP 官网 royalty 说明（35% / 70%）

本脚本只做算术，不判断你能否注册、能否上架。
所有数字请在上架前用 KDP 后台定价页复核一次。

★ 文件大小是硬输入：70% 档配送费 = $0.15/MB，35% 档的起价也随文件大小上移。
  所以每一次测算都要写明「用了多大的文件」，否则数字不可复核。本脚本的做法：
    - 每个输出都在首行打印「文件大小 = X MB（来源：--size-mb 传入 / --file 实测，N 字节）」；
    - 未传 --size-mb 也没传 --file 时，先用占位值 1.00 MB 算，并在首行打 ⚠ 提示这是占位值；
    - --file 可直接量本地文件的字节数，两种口径（1 MB=1e6 B / 1 MiB=2^20 B）都打印。

★ NOT VERIFIED：官方页没有说明这里的 MB 是 1e6 字节还是 2^20 字节，两者差约 4.86%。
  默认按 1 MB = 1,000,000 字节；要按 2^20 算加 --unit mib。上架前以 KDP 上传后
  显示的「转换后文件大小」为准，本脚本只用于定价前的算术。

用法：
  python3 -I kdp_royalty.py --table --size-mb 0.9
  python3 -I kdp_royalty.py --price 4.99 --size-mb 0.9
  python3 -I kdp_royalty.py --price 4.99 --file Book-Output/book.epub
  python3 -I kdp_royalty.py --price 4.99 --size-mb 0.9 --paper-cost 2.65
  python3 -I kdp_royalty.py --price 4.99 --size-mb 0.9 --target 500 --months 3
"""

import argparse
import os
import sys

# ---------------------------------------------------------------- 规则常量
# 单位：USD。其他市场价带见 report() 末尾的市场表。
BAND = {
    "US": {
        "currency": "$",
        "p35": (0.99, 200.00),
        "p70": (2.99, 12.99),
        "delivery_per_mb": 0.15,   # 仅 70% 档
        "min_delivery": 0.01,
    },
}

# 其他市场的 70% 价带（据同一官方页整理，单源，NOT VERIFIED；35% 价带各国不同，此表只列 70% 下限上限）
OTHER_BANDS = [
    # 市场, 币种, 70% 下限, 70% 上限
    ("UK", "GBP", 1.77, 12.99),
    ("EU", "EUR", 2.69, 12.99),
    ("CA", "CAD", 2.99, 12.99),
    ("JP", "JPY", 250, 1650),
    ("IN", "INR", 99, 599),
    ("BR", "BRL", 5.99, 31.99),
]

# 35% 档按文件大小的起价（美国站；不超过 3 MB / 10 MB 的口径，NOT VERIFIED）
SIZE_FLOOR = [(3.0, 0.99), (10.0, 1.99), (float("inf"), 2.99)]

DEFAULT_MB = 1.00   # 占位值，仅在没有给出任何大小输入时使用


def size_floor(size_mb):
    for limit, floor in SIZE_FLOOR:
        if size_mb <= limit:
            return floor
    return 2.99


def measure(path, unit):
    """按本地文件字节数算大小。返回 (mb, bytes, 说明)。"""
    n = os.path.getsize(path)
    div = 1048576.0 if unit == "mib" else 1000000.0
    return n / div, n, "实测 %s（%d 字节）" % (path, n)


def size_header(size_mb, src, note):
    line = "文件大小 = %.2f MB（来源：%s）" % (size_mb, src)
    if note:
        line += " ⚠ " + note
    return line


def royalty(price, size_mb, plan="auto", market="US"):
    """返回 (plan, 到手金额, 说明)。plan=auto 时选到手更高的那一档。"""
    cfg = BAND[market]
    if plan == "auto":
        a = royalty(price, size_mb, "35", market)
        b = royalty(price, size_mb, "70", market)
        if b[1] is None:
            return ("auto", a[1], a[2])
        if a[1] is None:
            return ("auto", b[1], b[2])
        if b[1] > a[1]:
            return ("auto", b[1], b[2])
        return ("auto", a[1], a[2])

    if plan == "70":
        lo, hi = cfg["p70"]
        if not (lo <= price <= hi + 1e-9):
            return ("70", None,
                    "超出 70%% 价带 %s%.2f-%s%.2f，此价只能走 35%%"
                    % (cfg["currency"], lo, cfg["currency"], hi))
        delivery = max(cfg["delivery_per_mb"] * size_mb, cfg["min_delivery"])
        net = price * 0.70 - delivery
        return ("70", max(net, 0.0),
                "含配送费 %s%.3f（%.2f MB × %.2f）"
                % (cfg["currency"], delivery, size_mb, cfg["delivery_per_mb"]))

    # 35%
    lo, hi = cfg["p35"]
    floor = size_floor(size_mb)
    if price < max(lo, floor) - 1e-9 or price > hi + 1e-9:
        return ("35", None,
                "低于该文件大小的 35%% 起价 %s%.2f，或高于 %s%.2f"
                % (cfg["currency"], max(lo, floor), cfg["currency"], hi))
    return ("35", price * 0.35, "无配送费")


def paper(list_price, print_cost, rate=0.60):
    """纸书：版税 = 定价 × 费率 − 印刷成本。print_cost 必须从 KDP 定价页抄。"""
    return list_price * rate - print_cost


def resolve_size(args):
    """决定本次测算用的文件大小。返回 (mb, src, note)。"""
    if args.file:
        mb, n, src = measure(args.file, args.unit)
        return mb, src, ""
    if args.size_mb is not None:
        return args.size_mb, "--size-mb 传入 %.2f MB" % args.size_mb, ""
    return (DEFAULT_MB, "未给大小，用占位值 %.2f MB" % DEFAULT_MB,
            "这是占位值，不是本书的实际大小；请用 --file 量实际文件或 --size-mb 填 KDP 显示的转换后大小")


def report(args):
    size, src, note = resolve_size(args)
    print(size_header(size, src, note))
    print("市场 %s｜35%% 档该大小的起价：$%.2f" % (args.market, size_floor(size)))
    print()

    if args.table:
        print("价位    35%档到手   70%档到手   自动选")
        print("-" * 46)
        for cents in range(99, 1500, 100):
            p = cents / 100.0
            _, n35, _ = royalty(p, size, "35", args.market)
            _, n70, _ = royalty(p, size, "70", args.market)
            s35 = ("%10.2f" % n35) if n35 is not None else "         —"
            s70 = ("%10.2f" % n70) if n70 is not None else "         —"
            auto = max([x for x in (n35, n70) if x is not None] or [0])
            print("$%-6.2f %s %s %10.2f" % (p, s35, s70, auto))
        print()
        print("注：70% 档有 40 个「70% 地区」限制，40 地区之外按 35% 计；")
        print("    若同时出纸书，电子书定价须至少比纸书低 20%。")

    if args.price:
        print("定价 $%.2f" % args.price)
        for plan in ("35", "70", "auto"):
            p, net, note2 = royalty(args.price, size, plan, args.market)
            if net is None:
                print("  %-4s 档：不适用 —— %s" % (p, note2))
            else:
                print("  %-4s 档：到手 $%.2f（%.1f%%）—— %s"
                      % (p, net, net / args.price * 100, note2))
        print()

        if args.paper_cost is not None:
            net = paper(args.price, args.paper_cost)
            print("纸书同价 $%.2f，印刷成本 $%.2f → 到手 $%.2f"
                  % (args.price, args.paper_cost, net))
            if net <= 0:
                print("  ⚠ 定价低于印刷成本，卖一本亏一本。")
            print()

        if args.target:
            _, net, _ = royalty(args.price, size, "auto", args.market)
            if net and net > 0:
                months = max(args.months, 1)
                need = args.target / net
                print("目标：%d 个月内 $%.0f 到手，按每本 $%.2f" % (months, args.target, net))
                print("  → 需卖出 %.0f 本，即每月约 %.0f 本" % (need, need / months))
                print("  （未计退款、促销、地区差价、预扣税）")

    print()
    print("其他市场 70% 价带（单源，NOT VERIFIED）：")
    for m, cur, lo, hi in OTHER_BANDS:
        print("  %-3s %s%.2f - %s%.2f" % (m, cur, lo, cur, hi))
    print()
    print("未计入：预扣税（非美国税收居民通常填 W-8BEN，协定税率需以 KDP 税表页为准）、")
    print("        汇率、单笔电汇费、退款、KDP Select 独家约束、KENP 分成。")


def main(argv=None):
    ap = argparse.ArgumentParser(description="KDP 到手金额测算（不做合规判断）")
    ap.add_argument("--price", type=float, help="电子书定价 USD，如 6.99")
    ap.add_argument("--size-mb", type=float, default=None,
                    help="转换后文件大小 MB（优先用 KDP 上传后显示的值）")
    ap.add_argument("--file", default=None,
                    help="本地文件路径，按字节数实测大小（与 --size-mb 二选一，--file 优先）")
    ap.add_argument("--unit", default="mb", choices=["mb", "mib"],
                    help="--file 实测时的换算口径：mb=1e6 字节（默认），mib=2^20 字节")
    ap.add_argument("--market", default="US", choices=sorted(BAND))
    ap.add_argument("--paper-cost", type=float, default=None,
                    help="纸书印刷成本 USD，从 KDP 定价页抄实际值，勿估")
    ap.add_argument("--target", type=float, default=None, help="目标到手金额 USD")
    ap.add_argument("--months", type=int, default=12, help="目标周期月数（默认 12）")
    ap.add_argument("--table", action="store_true", help="列价位表")
    args = ap.parse_args(argv)

    if args.file and not os.path.exists(args.file):
        print("找不到文件：%s" % args.file)
        return 2
    if not (args.table or args.price):
        ap.print_help()
        return 2
    report(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
