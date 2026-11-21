#!/usr/bin/env python3
"""从 book-config.json 和 metadata-draft.json 生成 KDP 上架信息草稿，并按字段限制检查。

用法：
  kdp_metadata.py <项目目录>

metadata-draft.json 由人或 AI 先写（描述、关键词、分类），本脚本只检查、不代写卖点。
字段限制（书名＋副标题 200、描述 4000、关键词 7、分类 3）是按 KDP 帮助页的常见口径写的，
本脚本没有逐项核实（NOT VERIFIED）；上架前须由作者在 KDP 后台按当时的页面再核。
输出 Book-Output/kdp-metadata.json；有 ERROR 时退出码为 1。
"""
import json
import re
import sys
from pathlib import Path

DRAFT_TEMPLATE = {
    "description": "",
    "keywords": [],
    "categories": [],
    "price_usd": None,
    "series": "",
}
SUPPORTED_EDITION = {"en", "zh-hant", "ja", "de", "fr", "es", "it", "pt", "nl"}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    cfg = json.loads((root / "book-config.json").read_text(encoding="utf-8"))
    dp = root / "metadata-draft.json"
    if not dp.exists():
        dp.write_text(json.dumps(DRAFT_TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sys.exit(f"已建空白 {dp}，先填描述、关键词、分类再运行")
    d = json.loads(dp.read_text(encoding="utf-8"))
    errs, warns = [], []

    lang = cfg.get("edition_lang", "").lower()
    if not lang:
        errs.append("上架语言未定（由作者定）")
    elif lang in ("zh-hans", "zh-cn", "zh"):
        errs.append("上架语言是简体中文：KDP 不收")
    elif lang not in SUPPORTED_EDITION:
        warns.append(f"上架语言 {lang} 未在本脚本的已知列表里，请到 KDP 帮助页核对")
    formats = cfg.get("formats", ["ebook"])
    if lang == "zh-hant" and any(f != "ebook" for f in formats):
        errs.append("繁体中文在 KDP 只能出电子书（以 KDP 帮助页为准），formats 里却有其他版本")
    if any(f not in ("ebook", "paperback", "audiobook") for f in formats):
        errs.append(f"formats 只认 ebook、paperback、audiobook：{formats}")

    title, sub = cfg.get("title", ""), cfg.get("subtitle", "")
    if len(title) + len(sub) > 200:
        errs.append(f"书名＋副标题 {len(title) + len(sub)} 字符，超过 200")
    if re.search(r"[一-鿿]", title) and lang == "en":
        warns.append("英文版的书名还是中文：上架前要定英文书名")
    if "【" in cfg.get("author", ""):
        errs.append("署名还是占位，待作者定笔名")

    desc = d.get("description", "")
    plain = re.sub(r"<[^>]+>", "", desc)
    if not plain.strip():
        errs.append("描述为空")
    if len(desc) > 4000:
        errs.append(f"描述 {len(desc)} 字符，超过 4000")
    if re.search(r"https?://|www\.|@", plain):
        errs.append("描述里有网址或邮箱")
    if re.search(r"best.?sell|#1|畅销", plain, re.I):
        warns.append("描述里有「畅销」类字样：没有实际排名依据不要写")

    kw = d.get("keywords", [])
    if len(kw) > 7:
        errs.append(f"关键词 {len(kw)} 个，超过 7")
    for k in kw:
        if len(k) > 50:
            errs.append(f"关键词过长（{len(k)}）：{k}")
        if re.search(r"kindle|amazon|free|bestsell", k, re.I):
            errs.append(f"关键词含平台名或误导词：{k}")
    if len(d.get("categories", [])) > 3:
        errs.append("分类超过 3 个")

    ai = cfg.get("ai_disclosure", {})
    for k in ("text", "images", "translation"):
        if ai.get(k) not in ("ai-generated", "ai-assisted", "none"):
            errs.append(f"AI 披露的 {k} 一项未填（ai-generated / ai-assisted / none）")
    if ai.get("text") == "ai-assisted":
        warns.append("文字标为 AI 辅助：只有作者自己写、AI 只润色时才成立；多 AI 起草应标 AI 生成")

    meta = {
        "title": title, "subtitle": sub, "author": cfg.get("author"),
        "language": lang, "formats": formats, "kdp_select": cfg.get("kdp_select", False),
        "description": desc, "keywords": kw, "categories": d.get("categories", []),
        "price_usd": d.get("price_usd"), "ai_disclosure": ai,
        "status": "DRAFT — 上架、定价、Select 都须作者在 KDP 后台本人操作",
        "errors": errs, "warnings": warns,
    }
    out = root / "Book-Output" / "kdp-metadata.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for e in errs:
        print("  ERROR", e)
    for w in warns:
        print("  WARN ", w)
    print(f"ERROR {len(errs)}，WARN {len(warns)}；输出 {out}")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
