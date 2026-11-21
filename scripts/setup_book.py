#!/usr/bin/env python3
"""新建一本书的项目目录。

用法：
  setup_book.py <项目目录> --title 书名 --type ai-practice|one-person-company|laozi-study|essay
                [--subtitle 副标题] [--author 署名] [--lang zh-Hans] [--edition-lang en]
                [--chapters 10] [--select] [--repo 记录仓路径]

只新建，不覆盖：目录里已有 book-config.json 就退出。
"""
import argparse
import json
import re
import sys
from pathlib import Path

TYPES = ("ai-practice", "one-person-company", "laozi-study", "essay")
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def slugify(s):
    s = re.sub(r"[^\w\s-]", "", s.lower(), flags=re.ASCII)
    return re.sub(r"[\s_-]+", "-", s).strip("-") or "book"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--author", default="【待 Human 定笔名】")
    ap.add_argument("--type", choices=TYPES, required=True)
    ap.add_argument("--lang", default="zh-Hans", help="写作底稿语言")
    ap.add_argument("--edition-lang", default="", help="上架版本语言（作者定）；KDP 不收简体中文")
    ap.add_argument("--formats", default="ebook", help="逗号分隔：ebook,paperback,audiobook；默认先出电子书")
    ap.add_argument("--chapters", type=int, default=10)
    ap.add_argument("--outline", choices=("evidence", "a-to-b"), default="evidence",
                    help="大纲模板：证据锚点式，或 A 点痛点 → B 点理想状态")
    ap.add_argument("--select", action="store_true", help="计划加入 KDP Select（Select 期内 Kindle 电子书只能经 KDP 和公共图书馆发行，书的内容不要以数字形式发到其他渠道）")
    ap.add_argument("--slug", default="")
    ap.add_argument("--repo", default="", help="证据所在的记录仓（git）路径，供 check_book.py 核对")
    a = ap.parse_args()

    root = Path(a.project)
    if (root / "book-config.json").exists():
        sys.exit(f"{root}/book-config.json 已存在，不覆盖")
    (root / "chapters").mkdir(parents=True, exist_ok=True)
    (root / "Book-Output").mkdir(exist_ok=True)
    (root / "public").mkdir(exist_ok=True)

    chapters = [f"ch{i:02d}.md" for i in range(1, a.chapters + 1)] + ["appendix.md"]
    cfg = {
        "title": a.title,
        "subtitle": a.subtitle,
        "author": a.author,
        "book_type": a.type,
        "draft_lang": a.lang,
        "edition_lang": a.edition_lang,
        "slug": a.slug or slugify(a.title),
        "formats": [x.strip() for x in a.formats.split(",") if x.strip()],
        "kdp_select": a.select,
        "evidence_repo": a.repo,
        "chapters": chapters,
        "toc_items": ([f"Chapter {i}" for i in range(1, a.chapters + 1)] + ["Appendix"]) if a.lang.startswith("en")
                     else ([f"第 {i} 章" for i in range(1, a.chapters + 1)] + ["附录"]),
        "targets": ({"chapter_min": 2000, "chapter_max": 4500, "appendix_min": 500, "appendix_max": 2000}
                    if a.lang.startswith("en") else
                    {"chapter_min": 3000, "chapter_max": 6000, "appendix_min": 1000, "appendix_max": 3000}),
        "ai_disclosure": {"text": "ai-generated", "images": "none", "translation": "ai-generated"},
        "public_sources": [],
        "cover": "",
        "status": "DRAFT",
    }
    (root / "book-config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tpl_name = {"laozi-study": "chapter-laozi.md", "essay": "chapter-essay.md"}.get(a.type, "chapter-practice.md")
    tpl = (TEMPLATES / tpl_name).read_text(encoding="utf-8")
    for i, fn in enumerate(chapters, 1):
        p = root / "chapters" / fn
        if p.exists():
            continue
        en = a.lang.startswith("en")
        head = ("# Appendix" if en else "# 附录") if fn == "appendix.md" \
            else (f"# Chapter {i} 【title】" if en else f"# 第 {i} 章 【章名】")
        p.write_text(tpl.replace("{{HEAD}}", head), encoding="utf-8")

    outline = root / "outline.md"
    if not outline.exists():
        name = "outline-a-to-b.md" if a.outline == "a-to-b" else "outline.md"
        outline.write_text((TEMPLATES / name).read_text(encoding="utf-8")
                           .replace("{{TITLE}}", a.title), encoding="utf-8")
    print(f"已建：{root}（{len(chapters)} 个章节文件，类型 {a.type}，上架语言 {a.edition_lang or '待作者定'}）")


if __name__ == "__main__":
    main()
