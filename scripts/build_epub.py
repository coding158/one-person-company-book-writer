#!/usr/bin/env python3
"""把定稿章节打成 KDP 上传用的 EPUB 3（KDP 电子书封面只收 JPG/TIFF，PNG 封面会先转成 JPG）。

用法：
  build_epub.py <项目目录> [--out 输出目录] [--keep-refs]

读 book-config.json：title、subtitle、author、slug、edition_lang、chapters，以及 cover（封面图相对项目目录的路径，
.jpg/.jpeg 直接用，.png 用 macOS 自带的 sips 转 JPG）。
可选 chapters/front-matter.md：第一个「# 」之前是版权页，之后是说明页；没有这个文件就不出这两页。
顺序：封面、书名页、版权页、说明页、目录、chapters。默认去掉 [ev: …] 证据标记（借用同目录 merge_book.py 的 EV_RE 和 md_to_html）。
章节文件只读；输出默认写到 Book-Output/。
"""
import argparse
import datetime
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
CSS = ("body{font-family:serif;line-height:1.5}h1{margin-top:1.5em}blockquote{margin:1em 1.5em;font-style:normal}"
       ".tp{text-align:center;margin-top:20%}.tp h1{font-size:2em}.sub{font-size:1.2em;margin:1em 0}"
       ".au{font-size:1.2em;margin-top:2em}")


def load_merge_book():
    spec = importlib.util.spec_from_file_location("merge_book", HERE / "merge_book.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def page(title, body, lang):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">'
            f'<head><meta charset="utf-8"/><title>{html.escape(title)}</title>'
            f'<link rel="stylesheet" type="text/css" href="style.css"/></head><body>{body}</body></html>')


def cover_jpg(src, out_dir):
    if src.suffix.lower() in (".jpg", ".jpeg"):
        return src
    if src.suffix.lower() != ".png":
        sys.exit(f"封面只认 .jpg/.jpeg/.png：{src}")
    if not shutil.which("sips"):
        sys.exit("PNG 封面要用 macOS 的 sips 转 JPG；不在 macOS 上请先自己转成 JPG，再把 cover 指向它")
    dst = out_dir / (src.stem + ".jpg")
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "95", str(src), "--out", str(dst)],
                   check=True, capture_output=True)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--out", default="", help="输出目录，默认 <项目目录>/Book-Output")
    ap.add_argument("--keep-refs", action="store_true", help="保留 [ev: …] 标记，供内部审稿用")
    a = ap.parse_args()

    root = Path(a.project)
    out = Path(a.out) if a.out else root / "Book-Output"
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((root / "book-config.json").read_text(encoding="utf-8"))
    mb = load_merge_book()
    lang = cfg.get("edition_lang") or cfg.get("draft_lang") or "en"
    en = lang.lower().startswith("en")
    title, sub, author = cfg["title"], cfg.get("subtitle", ""), cfg.get("author", "")
    if not cfg.get("cover"):
        sys.exit("book-config.json 没有 cover（封面图路径）")
    cj = cover_jpg(root / cfg["cover"], out)

    chap = []
    for fn in cfg["chapters"]:
        p = root / "chapters" / fn
        if not p.exists():
            sys.exit(f"缺章节文件：{p}")
        t = p.read_text(encoding="utf-8")
        if not a.keep_refs:
            t = mb.EV_RE.sub("", t)
        m = re.search(r"^# (.*)$", t, re.M)
        chap.append((Path(fn).stem, m.group(1) if m else Path(fn).stem, mb.md_to_html(t)))

    files = {"cover.xhtml": page("Cover", '<div style="text-align:center"><img src="cover.jpg" alt="Cover" '
                                          'style="max-width:100%"/></div>', lang),
             "title.xhtml": page(title, f'<section class="tp" epub:type="titlepage"><h1>{html.escape(title)}</h1>'
                                        f'<p class="sub">{html.escape(sub)}</p><p class="au">{html.escape(author)}</p>'
                                        "</section>", lang)}
    order = ["cover.xhtml", "title.xhtml"]
    fmp = root / "chapters" / "front-matter.md"
    if fmp.exists():
        fm = fmp.read_text(encoding="utf-8")
        cp, note = fm.split("\n# ", 1) if "\n# " in fm else (fm, "")
        files["copyright.xhtml"] = page("Copyright", '<section epub:type="copyright-page">' + mb.md_to_html(cp)
                                        + "</section>", lang)
        order.append("copyright.xhtml")
        if note:
            files["note.xhtml"] = page(note.split("\n", 1)[0], mb.md_to_html("# " + note), lang)
            order.append("note.xhtml")
    toc_title = "Contents" if en else "目录"
    nav = "".join(f'<li><a href="{c}.xhtml">{html.escape(h)}</a></li>' for c, h, _ in chap)
    files["nav.xhtml"] = page(toc_title, f'<nav epub:type="toc" id="toc"><h1>{toc_title}</h1><ol>{nav}</ol></nav>', lang)
    order.append("nav.xhtml")
    for cid, h1, body in chap:
        files[f"{cid}.xhtml"] = page(h1, body.replace("<br>", "<br/>"), lang)
        order.append(f"{cid}.xhtml")
    for v in files.values():
        ET.fromstring(v.encode())  # 每页都须是合法 XML

    slug = cfg.get("slug", "book") + ("-review" if a.keep_refs else "")
    bid = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"{slug}-{lang}"))
    mod = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    navp = ' properties="nav"'
    man = "".join(f'<item id="i{i}" href="{f}" media-type="application/xhtml+xml"'
                  f'{navp if f == "nav.xhtml" else ""}/>' for i, f in enumerate(order))
    opf = ('<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           f'unique-identifier="bid" xml:lang="{lang}"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="bid">{bid}</dc:identifier><dc:title>{html.escape(title)}</dc:title>'
           f'<dc:creator>{html.escape(author)}</dc:creator><dc:language>{lang}</dc:language>'
           f'<meta property="dcterms:modified">{mod}</meta><meta name="cover" content="cimg"/></metadata>'
           f'<manifest>{man}<item id="css" href="style.css" media-type="text/css"/>'
           '<item id="cimg" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/></manifest>'
           "<spine>" + "".join(f'<itemref idref="i{i}"/>' for i in range(len(order))) + "</spine></package>")
    ET.fromstring(opf.encode())

    ep = out / f"{slug}.epub"
    with zipfile.ZipFile(ep, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   "</rootfiles></container>", compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS, compress_type=zipfile.ZIP_DEFLATED)
        z.write(cj, "OEBPS/cover.jpg", compress_type=zipfile.ZIP_DEFLATED)
        for k, v in files.items():
            z.writestr("OEBPS/" + k, v, compress_type=zipfile.ZIP_DEFLATED)
    text = " ".join(re.sub("<[^>]+>", " ", files[f"{c}.xhtml"]) for c, _, _ in chap)
    print(f"已出：{ep}（{ep.stat().st_size} 字节，{len(chap)} 章，正文约 {len(html.unescape(text).split())} 词）；封面 {cj}")


if __name__ == "__main__":
    main()
