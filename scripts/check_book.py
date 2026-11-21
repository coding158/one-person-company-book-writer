#!/usr/bin/env python3
"""书稿检查：证据、红线、篇幅、站外公开占比。只读书稿，只写 Book-Output/check-report.json。

用法：
  check_book.py <项目目录> [--repo 记录仓路径] [--public 文件 ...] [--stage draft|final]

证据标记写在段落末尾：[ev: 1a2b3c4, MSG-20250101-090000-01, notes/2025-01-01.md]
  提交 SHA 用 git cat-file 核对；MSG-… 编号在记录仓 HEAD 里找「message_id: 编号」一行；其他按仓内路径核对。
不给记录仓（--repo 或 book-config.json 的 evidence_repo）时只查红线，不核对证据。
老子研究类可另用出处标记：[src: 帛书甲本 第 12 行]
退出码：有 ERROR 为 1，否则 0。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

EV_RE = re.compile(r"\[ev:\s*([^\]]+)\]")
SRC_RE = re.compile(r"\[src:\s*([^\]]+)\]")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
MSG_RE = re.compile(r"^MSG-\d{8}-\d{6}-\d{2}$")

SECRETS = {
    "GitHub PAT": r"\b(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})",
    "OpenAI sk-": r"\bsk-[A-Za-z0-9]{20,}",
    "Anthropic sk-ant-": r"\bsk-ant-[A-Za-z0-9\-_]{20,}",
    "Notion secret_/ntn_": r"\b(secret_[A-Za-z0-9]{30,}|ntn_[A-Za-z0-9]{30,})",
    "Slack xox": r"\bxox[baprs]-[A-Za-z0-9\-]{10,}",
    "AWS AKIA": r"\bAKIA[0-9A-Z]{16}\b",
    "Google AIza": r"\bAIza[0-9A-Za-z\-_]{35}",
    "PRIVATE KEY 块": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "password= 赋值": r"(?i)\b(password|passwd|pwd)\s*[=:]\s*[^\s'\"]{8,}",
    "Bearer 长串": r"(?i)\bBearer\s+[A-Za-z0-9\-_\.]{20,}",
}
# (级别, 名称, 正则)
REDLINES = [
    ("ERROR", "邮箱地址", r"[\w.+-]+@[\w-]+\.[\w.]+"),
    ("ERROR", "手机号", r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    ("ERROR", "以书换评论", r"(免费|赠).{0,12}(换|求|拿).{0,6}评论|free.{0,30}(for|in exchange for).{0,10}review"),
    ("ERROR", "疗效承诺", r"治愈|根治|包治|guaranteed cure"),
    ("WARN", "收入或销量数字（须有出处并核实）", r"(\$\s?\d[\d,.]*\s?[MKk万]?|\d+\s?万美元|月入\s?\d|BSR\s?\d)"),
    ("WARN", "畅销承诺", r"保证畅销|必成畅销|guaranteed best.?sell"),
    ("WARN", "插图（须写明来源与授权；图版一律不开放）", r"!\[[^\]]*\]\([^)]*\)"),
    ("WARN", "提到图版（只可文字讨论，不可附图）", r"图版|plate photo"),
]
PLACEHOLDER_HUMAN = re.compile(r"【待 ?Human[^】]*】")
PLACEHOLDER_ANY = re.compile(r"【[^】]{1,40}】")
TO_VERIFY = re.compile(r"【待核[^】]*】|NOT VERIFIED")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def is_placeholder(ref):
    return ref.startswith("【") or ref.strip("…. ") == ""


def verify_ref(repo, ref, cache):
    if ref in cache:
        return cache[ref]
    if SHA_RE.match(ref):
        ok = git(repo, "cat-file", "-e", f"{ref}^{{commit}}").returncode == 0
    elif MSG_RE.match(ref):
        ok = git(repo, "grep", "-q", "-F", f"message_id: {ref}", "HEAD").returncode == 0
    else:
        ok = git(repo, "cat-file", "-e", f"HEAD:{ref}").returncode == 0
    cache[ref] = ok
    return ok


def length(text):
    body = EV_RE.sub("", SRC_RE.sub("", text))
    cjk = len(re.findall(r"[一-鿿]", body))
    words = len(re.findall(r"[A-Za-z][A-Za-z'-]*", body))
    return cjk + words


def ngrams(text, n=8):
    s = re.sub(r"\s+", "", EV_RE.sub("", SRC_RE.sub("", text)))
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def sections(text):
    """按二级标题切段；返回 (标题, 正文)。一级标题前的导语算一段。"""
    parts, cur, buf = [], "（导语）", []
    for line in text.splitlines():
        if line.startswith("## "):
            parts.append((cur, "\n".join(buf)))
            cur, buf = line[3:].strip(), []
        elif not line.startswith("# "):
            buf.append(line)
    parts.append((cur, "\n".join(buf)))
    return [(h, b) for h, b in parts if b.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--repo", default="", help="证据所在的记录仓（git）路径")
    ap.add_argument("--public", nargs="*", default=[])
    ap.add_argument("--stage", choices=("draft", "final"), default="draft")
    a = ap.parse_args()

    root = Path(a.project)
    cfg = json.loads((root / "book-config.json").read_text(encoding="utf-8"))
    repo = a.repo or cfg.get("evidence_repo", "")
    if repo and git(repo, "rev-parse", "--git-dir").returncode != 0:
        sys.exit(f"--repo {repo} 不是 git 仓库")
    secrets = SECRETS
    laozi = cfg.get("book_type") == "laozi-study"
    essay = cfg.get("book_type") == "essay"
    t = cfg.get("targets", {})

    findings, cache, chapters_out = [], {}, []
    book_text = []

    def add(level, where, what):
        findings.append({"level": level, "where": where, "what": what})

    outline = root / "outline.md"
    if repo and outline.exists():
        for m in EV_RE.findall(outline.read_text(encoding="utf-8")):
            for r in (x.strip() for x in m.split(",")):
                if r and not is_placeholder(r) and not verify_ref(repo, r, cache):
                    add("ERROR", "outline.md", f"证据锚点对不上记录仓：{r}")

    for fn in cfg["chapters"]:
        p = root / "chapters" / fn
        if not p.exists():
            add("ERROR", fn, "章节文件不存在")
            continue
        text = p.read_text(encoding="utf-8")
        book_text.append(text)
        n = length(text)
        lo, hi = (t.get("appendix_min", 0), t.get("appendix_max", 10**9)) if fn == "appendix.md" \
            else (t.get("chapter_min", 0), t.get("chapter_max", 10**9))
        if not lo <= n <= hi:
            add("WARN", fn, f"篇幅 {n}，目标 {lo}–{hi}（汉字＋英文词）")

        refs = [r.strip() for m in EV_RE.findall(text) for r in m.split(",")
                if r.strip() and not is_placeholder(r.strip())]
        bad = [r for r in refs if repo and not verify_ref(repo, r, cache)]
        for r in bad:
            add("ERROR", fn, f"证据引用对不上记录仓：{r}")
        no_ev = [] if essay else [h for h, b in sections(text)
                 if length(b) >= 80 and not EV_RE.search(b) and not (laozi and SRC_RE.search(b))]
        for h in no_ev:
            add("WARN", fn, f"「{h}」一段没有证据标记")

        for name, pat in secrets.items():
            if re.search(pat, text):
                add("ERROR", fn, f"疑似秘密：{name}")
        for level, name, pat in REDLINES:
            k = len(re.findall(pat, text, flags=re.I))
            if k:
                add(level, fn, f"{name}：{k} 处")

        hum = len(PLACEHOLDER_HUMAN.findall(text))
        other = sum(1 for m in PLACEHOLDER_ANY.findall(text) if not PLACEHOLDER_HUMAN.fullmatch(m))
        tov = len(TO_VERIFY.findall(text))
        lvl = "ERROR" if a.stage == "final" else "INFO"
        if hum:
            add(lvl, fn, f"待 Human 补写：{hum} 处")
        if other:
            add(lvl, fn, f"其他占位：{other} 处")
        if tov:
            add(lvl, fn, f"待核：{tov} 处")
        chapters_out.append({"file": fn, "length": n, "evidence_refs": len(refs),
                             "bad_refs": bad, "sections_without_evidence": no_ev})

    pubs = [Path(x) for x in list(cfg.get("public_sources", [])) + a.public]
    overlap = None
    if pubs:
        book = ngrams("\n".join(book_text))
        pub = set()
        for p in pubs:
            pp = p if p.is_absolute() else root / p
            if not pp.exists():
                add("ERROR", str(p), "站外公开文本找不到")
                continue
            pub |= ngrams(pp.read_text(encoding="utf-8"))
        if book:
            overlap = round(len(book & pub) / len(book), 4)
            if cfg.get("kdp_select") and overlap > 0.10:
                add("ERROR", "全书", f"与站外公开文本重合 {overlap:.1%}，超过 KDP Select 的 10%")
            elif overlap > 0.05:
                add("WARN", "全书", f"与站外公开文本重合 {overlap:.1%}")
    elif cfg.get("kdp_select"):
        add("WARN", "全书", "计划进 KDP Select，但没给站外公开文本，无法算重合占比")

    if cfg.get("edition_lang", "").lower() in ("zh-hans", "zh-cn", "zh"):
        add("ERROR", "book-config.json", "上架语言是简体中文：KDP 不收简体中文")

    report = {
        "project": str(root), "stage": a.stage, "evidence_repo": repo or None,
        "refs_checked": len(cache), "refs_bad": sum(1 for v in cache.values() if not v),
        "public_overlap": overlap, "chapters": chapters_out, "findings": findings,
    }
    out = root / "Book-Output" / "check-report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    count = {k: sum(1 for f in findings if f["level"] == k) for k in ("ERROR", "WARN", "INFO")}
    print(f"章节 {len(chapters_out)}；证据引用核对 {len(cache)} 个，对不上 {report['refs_bad']} 个"
          + ("（未给记录仓，未核对）" if not repo else ""))
    if overlap is not None:
        print(f"站外公开重合：{overlap:.1%}")
    for f in findings:
        if f["level"] != "INFO":
            print(f"  {f['level']:5} {f['where']}：{f['what']}")
    print(f"ERROR {count['ERROR']}，WARN {count['WARN']}，INFO {count['INFO']}；报告 {out}")
    sys.exit(1 if count["ERROR"] else 0)


if __name__ == "__main__":
    main()
