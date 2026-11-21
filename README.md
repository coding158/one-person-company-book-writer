# one-person-company-book-writer

A writing workflow (an AI-agent "skill") for turning work you actually did into a book, with every claim tied to a record you can check.

一套写书流程：把自己真实做过的事写成书，书里每段经历都挂可核对的证据。

## What it does / 它做什么

- **Evidence first.** Each paragraph about something that happened ends with an evidence mark such as `[ev: 1a2b3c4]`, pointing at a commit, a message id or a file in your own record repository. `check_book.py` verifies every mark against that repository.
- **Red lines checked automatically.** Secrets, email addresses and phone numbers, reviews in exchange for free books, health-cure promises, unverified income figures, unlicensed third-party images, and KDP Select's 10% limit on content published elsewhere.
- **The author decides.** Templates leave `【待 Human 补写】` ("to be written by the author") slots for first-hand stories; the scripts never write them. Publishing, pricing and KDP Select stay with the author.
- **Output.** Merged Markdown/HTML (optional PDF via playwright), an EPUB 3 for KDP upload, a KDP metadata draft with field checks, and a royalty calculator that always prints the file size it used.

- **先证据：** 段末挂 `[ev: …]`，指向你自己记录仓里的提交、消息编号或文件；`check_book.py` 逐个核对。
- **红线自动查：** 秘密、邮箱手机号、以书换评论、疗效承诺、未核实的收入数字、未授权的第三方图像、KDP Select 站外公开 10% 上限。
- **作者拍板：** 亲历段落留给作者写，脚本不代写；上架、定价、Select 由作者本人操作。
- **产出：** 合并的 Markdown/HTML（可选 PDF）、KDP 上传用 EPUB 3、上架信息草稿、版税测算。

## Quick start / 快速开始

Python 3.8+ standard library only.

```bash
S=scripts
python3 -I $S/setup_book.py my-book --title "My Book" --type ai-practice --lang en --edition-lang en --select
python3 -I $S/check_book.py my-book --repo /path/to/your/record-repo
python3 -I $S/merge_book.py my-book
python3 -I $S/kdp_royalty.py --price 4.99 --size-mb 0.9
```

Try it on the fictional example: `python3 -I scripts/check_book.py examples/demo` (no record repository given, so only red lines are checked).

See `SKILL.md` for the full workflow and `references/redlines.md` for the rules and where they come from.

## Limits / 局限

- Platform rules (KDP price bands, delivery fees, metadata limits, language support) are written as of late 2026 and marked NOT VERIFIED where they come from a single source. Check the platform's own pages before publishing.
- The red-line checks are regular expressions: they catch common cases, not every case.
- Book types are `ai-practice`, `one-person-company`, `laozi-study` (classical-text study) and `essay`. Prose templates are mostly in Chinese.
- This is not legal, tax or financial advice.

## Credits / 致谢

The staged structure was inspired by duchangyu/best-selling-book-writer-skill. No code or text was copied; this project is a rewrite with a different goal (writing up real work with evidence, rather than producing books in bulk).

## License / 许可

Code (`scripts/`): MIT — see `LICENSE`. Documentation, templates and examples: CC BY 4.0 — see `LICENSE-docs.md` and `LICENSE-CC-BY-4.0.txt`.
