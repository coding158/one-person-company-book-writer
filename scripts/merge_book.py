#!/usr/bin/env python3
"""把章节合并成一份 Markdown 和一份 HTML；装了 playwright 时可加 --pdf 出 PDF。

用法：
  merge_book.py <项目目录> [--keep-refs] [--pdf]

默认去掉 [ev: …] 证据标记（记录仓读者看不到）；[src: …] 出处标记改成小字保留。
章节文件只读，不删不改；输出写到 Book-Output/。
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

EV_RE = re.compile(r"\s*\[ev:\s*[^\]]+\]")
SRC_RE = re.compile(r"\[src:\s*([^\]]+)\]")

CSS = """
body{font-family:"Noto Serif SC","Songti SC",Georgia,serif;max-width:40em;margin:2em auto;padding:0 1em;line-height:1.8;color:#222}
h1{page-break-before:always;margin-top:2.5em}h1.title{page-break-before:avoid;text-align:center;font-size:2.2em}
.subtitle,.author{text-align:center}.front{page-break-after:always}
blockquote{border-left:3px solid #999;margin:1em 0;padding:.2em 1em;color:#444}
code,pre{font-family:Menlo,Consolas,monospace;font-size:.9em}pre{background:#f4f4f4;padding:.8em;overflow-x:auto}
table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:.3em .6em}
.src{font-size:.8em;color:#666}
"""


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\[src:\s*([^\]]+)\]", r'<span class="src">（\1）</span>', s)
    return s


def md_to_html(md):
    out, para, lst, quote, code, table = [], [], None, [], None, []

    def flush():
        nonlocal para, lst, quote, table
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para = []
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
            lst = None
        if quote:
            out.append("<blockquote>" + md_to_html("\n".join(quote)) + "</blockquote>")
            quote = []
        if table:
            rows = [r for r in table if not re.match(r"^\|?\s*:?-+", r)]
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            if cells:
                h = "".join(f"<th>{inline(c)}</th>" for c in cells[0])
                b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:])
                out.append(f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>")
            table = []

    for line in md.splitlines():
        if code is not None:
            if line.startswith("```"):
                out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code = None
            else:
                code.append(line)
            continue
        if line.startswith("```"):
            flush()
            code = []
        elif not line.strip():
            flush()
        elif m := re.match(r"^(#{1,4})\s+(.*)", line):
            flush()
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif line.startswith(">"):
            if para or lst or table:
                flush()
            quote.append(line[1:].lstrip())
        elif line.lstrip().startswith("|"):
            if para or lst or quote:
                flush()
            table.append(line)
        elif m := re.match(r"^\s*([-*]|\d+\.)\s+(.*)", line):
            tag = "ol" if m.group(1)[0].isdigit() else "ul"
            if para or quote or table or (lst and lst[0] != tag):
                flush()
            lst = lst or (tag, [])
            lst[1].append(m.group(2))
        else:
            if lst or quote or table:
                flush()
            para.append(line.strip())
    flush()
    return "\n".join(out)


def is_en(cfg):
    return (cfg.get("edition_lang") or cfg.get("draft_lang", "")).lower().startswith("en")


def front_matter(cfg):
    ai = cfg.get("ai_disclosure", {})
    if is_en(cfg):
        return "\n".join([
            f"# {cfg['title']}", "", cfg.get("subtitle", ""), "", cfg.get("author", ""), "",
            "## How This Book Was Made", "",
            f"This book was written with the help of several AI assistants. Text: {ai.get('text', 'not stated')}; "
            f"images: {ai.get('images', 'not stated')}; translation: {ai.get('translation', 'not stated')}. "
            + ("Every quoted source text names its edition and location." if cfg.get("book_type") == "laozi-study"
               else "The cases come from the author's own working records; each event can be traced to the record made at the time."),
            "",
            "Platform rules and prices are as of the time of writing and may have changed. "
            "This book is not legal, financial or medical advice.",
        ])
    lines = [
        f"# {cfg['title']}",
        "",
        cfg.get("subtitle", ""),
        "",
        cfg.get("author", ""),
        "",
        "## 关于本书的写作方式",
        "",
        f"本书在多个 AI 助手参与下完成。文字：{ai.get('text', '未填')}；图片：{ai.get('images', '未填')}；"
        f"翻译：{ai.get('translation', '未填')}。"
        + ("书中引用的原文都注明了版本与出处。" if cfg.get("book_type") == "laozi-study"
           else "书中案例取自作者自己的协作仓库记录，事件都可回溯到当时的提交。"),
        "",
        "书中提到的平台规则与价格以写作时为准，可能已变化。本书不构成法律、财务或医疗建议。",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--keep-refs", action="store_true", help="保留 [ev: …] 标记，供内部审稿用")
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()

    root = Path(a.project)
    cfg = json.loads((root / "book-config.json").read_text(encoding="utf-8"))
    parts = []
    for fn in cfg["chapters"]:
        p = root / "chapters" / fn
        if not p.exists():
            sys.exit(f"缺章节文件：{p}")
        t = p.read_text(encoding="utf-8")
        parts.append(t if a.keep_refs else EV_RE.sub("", t))
    out_dir = root / "Book-Output"
    out_dir.mkdir(exist_ok=True)
    slug = cfg.get("slug", "book") + ("-review" if a.keep_refs else "")

    md = front_matter(cfg) + "\n\n" + "\n\n".join(parts)
    (out_dir / f"{slug}.md").write_text(md, encoding="utf-8")

    fm = md_to_html(front_matter(cfg)).replace("<h1>", '<h1 class="title">', 1)
    toc = "".join(f"<li>{html.escape(x)}</li>" for x in cfg.get("toc_items", []))
    body = "\n".join(md_to_html(x) for x in parts)
    doc = (f'<!doctype html><html lang="{cfg.get("draft_lang", "zh-Hans")}"><head><meta charset="utf-8">'
           f"<title>{html.escape(cfg['title'])}</title><style>{CSS}</style></head><body>"
           f'<section class="front">{fm}</section><section class="front"><h2>{"Contents" if is_en(cfg) else "目录"}</h2><ol>{toc}</ol></section>'
           f"{body}</body></html>")
    hp = out_dir / f"{slug}.html"
    hp.write_text(doc, encoding="utf-8")
    print(f"已出：{out_dir / (slug + '.md')}、{hp}")

    if a.pdf:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            sys.exit("没装 playwright，跳过 PDF（pip install playwright && playwright install chromium）")
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page()
            pg.goto(hp.resolve().as_uri())
            pg.pdf(path=str(out_dir / f"{slug}.pdf"), format="A5",
                   margin={"top": "18mm", "bottom": "18mm", "left": "15mm", "right": "15mm"})
            b.close()
        print(f"已出：{out_dir / (slug + '.pdf')}")


if __name__ == "__main__":
    main()
