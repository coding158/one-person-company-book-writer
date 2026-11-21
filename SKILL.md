---
name: one-person-company-book-writer
description: >
  一人公司写书流程：选题验证 → 带证据锚点的大纲 → 样章交作者 → 全稿 → 依次审稿 → 英文版 → KDP 上架信息草稿 → 合并 HTML/PDF/EPUB。
  面向几类书：AI 实务、一人公司、古籍研究（如《老子》）、观点随笔。书里的每段经历都要挂证据（记录仓里的提交 SHA、消息编号、路径），
  脚本会逐个核对；红线（秘密、隐私、第三方图像、以书换评论、疗效承诺、未核实的收入数字）自动拦。
  用于：写书、新建书稿项目、检查书稿、合并成书、生成 KDP 上架信息。
---

# one-person-company-book-writer

结构参考了 duchangyu/best-selling-book-writer-skill 的分阶段做法（那个仓库只在 README 末尾写了「MIT」，没有 LICENSE 文件和版权声明；本技能的代码和文字都是重写，没有照搬）。
和原版最大的不同：原版是「批量出自助书」，本技能是「把自己真实做过的事写成书」，所以多了一步证据核对，去掉了自动生成卖点文案。

**记录仓**：本技能假定你把工作记录（任务、回执、决定）存在一个自己的 git 仓库里，书里的证据标记就指向这个仓库。仓库可以是私有的，读者看不到；合并成书时证据标记默认去掉。

## 什么时候用

- 「写书」「新建书稿」「开一本新书」
- 「检查书稿」「核对证据」「看看能不能进 Select」
- 「合并成书」「出 PDF」「出 EPUB」
- 「生成 KDP 上架信息」

## 书的类型

| 类型 | `book_type` | 证据要求 | 章节模板 |
|---|---|---|---|
| AI 实务 | `ai-practice` | 每节至少一个 `[ev: …]`，指向记录仓的提交、消息编号或路径 | `templates/chapter-practice.md` |
| 一人公司 | `one-person-company` | 同上 | 同上 |
| 古籍研究 | `laozi-study` | 每节至少一个 `[src: …]`（版本＋章／行）或 `[ev: …]` | `templates/chapter-laozi.md` |
| 观点随笔（英文） | `essay` | 不强制证据标记；外部事实仍要 `[src: …]`，红线照查 | `templates/chapter-essay.md` |

**大纲两种：** `--outline evidence`（默认，每章列证据锚点）；`--outline a-to-b`（A 点痛点 → B 点理想状态，每章一步，适合观点书）。
**版本：** `--formats ebook`（默认，先出电子书）；纸质、有声可以后补。

## 流程

下表的角色是通用说法：「研究员」「起草员」「审稿员」可以是不同的 AI 助手，也可以是人；「作者」是书的署名人，所有要拍板的事由作者定。

| 步 | 做什么 | 谁做 | 关口 |
|---|---|---|---|
| 0 | 选题验证：同类书的书名、目录、定位（`templates/topic-validation.md`） | 研究员（能联网） | 只作参考，不推算销量 |
| 1 | `setup_book.py` 建项目，写 `outline.md`：每章要点＋证据锚点＋「待 Human 补写」 | 任一角色 | — |
| 2 | 写**一章样章**，跑 `check_book.py` 到 0 ERROR | 起草员 | 样章先交**作者人工看**，再定写不写全稿 |
| 3 | 写全稿 | 起草员 | — |
| 4 | 依次审稿：审稿员甲 → 乙 → 丙，每轮约 2 天 | 审稿员 | 意见冲突由最后一位审稿员拍板；冲突一方是最后一位审稿员时由作者拍板 |
| 5 | 英文直写的书：只译作者的中文亲历段落（`templates/localization-checklist.md`） | 起草员译，作者过目 | `check_book.py --stage final` 0 ERROR |
| 6 | `kdp_metadata.py` 出上架信息草稿 | 任一角色 | 描述、关键词由人或 AI 写，脚本只查不代写 |
| 7 | `merge_book.py --pdf` 合并成书；`build_epub.py` 出 KDP 上传用的 EPUB | 任一角色 | — |
| 8 | 上架、定价、Select、打样（`templates/launch-checklist.md`） | **作者本人** | AI 不代登录 KDP |

## 命令

```bash
S=<本技能目录>/scripts
python3 -I $S/setup_book.py <项目目录> --title "书名" --type ai-practice|one-person-company|laozi-study|essay \
        [--lang en] [--outline a-to-b] [--formats ebook] [--select] [--repo <记录仓路径>]
python3 -I $S/check_book.py <项目目录> [--repo <记录仓路径>] [--public 站外文本.md ...] [--stage final]
python3 -I $S/merge_book.py <项目目录> [--keep-refs] [--pdf]
python3 -I $S/build_epub.py <项目目录> [--out <输出目录>]
python3 -I $S/kdp_metadata.py <项目目录>
python3 -I $S/kdp_royalty.py --price 4.99 --size-mb 0.9 [--table] [--file <书稿文件>]
```

- 只用 Python 3.8+ 标准库；`merge_book.py --pdf` 另需 playwright，`build_epub.py` 把 PNG 封面转 JPG 时用 macOS 自带的 `sips`（封面已是 JPG 则不需要）。
- `check_book.py` 只读章节，报告写进 `Book-Output/check-report.json`；有 ERROR 退出码为 1。不给记录仓路径时不核对证据，只查红线。
- `kdp_royalty.py` 只做算术，输出第一行必打印所用文件大小；定价、Select、上架由作者定，脚本不代定。
- `merge_book.py`、`build_epub.py` 默认去掉 `[ev: …]`（记录仓读者看不到）；`--keep-refs` 出审稿用的版本。章节文件从不删改。

## 红线（`check_book.py` 自动查，详见 `references/redlines.md`）

| 级别 | 内容 |
|---|---|
| ERROR | 秘密（10 类常见密钥特征）；邮箱、手机号；以免费书或赠品换评论；疗效承诺；证据引用对不上记录仓；计划进 Select 而站外公开重合超过 10%；上架语言是简体中文 |
| WARN | 收入或销量数字；畅销承诺；插图；提到图版；某节没有证据；篇幅超出目标 |
| INFO → `--stage final` 时升为 ERROR | 「待 Human 补写」、其他【占位】、【待核】 |

## 写法

- 一段一件事。先讲发生了什么，再讲为什么，最后讲改了什么。
- 证据挂在段末：`[ev: 1a2b3c4]`、`[ev: MSG-20250101-090000-01]`、`[ev: notes/2025-01-01.md]`，可以多个，用逗号隔开。
- 作者本人的亲历和判断，AI 不代写，留「【待 Human 补写：…】」。
- 不写没核实的数字。要写，就挂出处；出处不可靠，就删掉。
- 每章结尾：一句话总结，加 3 条「这周可以试的」。

## 从「AI 写书＋KDP」类教程里借了什么、没借什么

| 借 | 不借 |
|---|---|
| A→B 大纲；每章留作者本人的故事；译文交叉校对；书名和封面先验证 | 「先免费拿 10 条评论」（与 Amazon 评论政策冲突）；把收入、销量、排名数字当事实写；「情绪幻想大于实用」的标题套路，标题可以抓人，但不许承诺书里没有的东西 |

## 不做的事

- 不注册平台，不登录 KDP，不定价，不发布。
- 不附未获授权的第三方图像（图版照片、裁片、描摹图等）。
- 不把书稿内容公开发到站外，除非已算过 Select 的 10% 占比，并经作者同意。
