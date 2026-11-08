**中文** | [English](README.en.md)

# 交班

一个会话就是一个员工，随时可以换。

会话会越聊越长，越长越慢、越贵，也越容易忘事。这个技能让 agent 换个做法：上下文保持短，要记住的东西写进仓库，跟着 git 提交走。新会话只读一份交接，就能接着干。

## 有论文撑着

NVIDIA 的《You don't need long context》（[arXiv 2611.05306](https://arxiv.org/abs/2611.05306)）在 13 个基准上测了 Claude Opus 4.5 和 GPT 5.6 Sol：

| 发现 | 数字 |
|---|---|
| 长程任务定期压成一份状态、开新对话，正确率基本不掉 | Opus −3.7 到 +5.6 分，GPT −3.3 到 +4.4 分；SWE-bench Verified 上 Opus 从 70.0 到 74.8 |
| 长输入按需读，比一次全塞进去更准 | Opus −0.4 到 +40.0 分，GPT +1.0 到 +30.9 分 |
| 每个对话只做一个动作，也不会崩 | Opus SWE-bench Verified 70.0 到 70.2 |
| 长上下文更贵 | 窗口从 16K 开到 256K，每个输出 token 贵 3.6 到 7 倍 |
| 最好的压缩是给下一段的简报，不是流水账 | 附录 A：原样的任务、现在在做什么、计划和完成条件 |

技能里每条规则都对到论文的某一节，细节和页码在 [`jiaoban/references/paper.md`](jiaoban/references/paper.md)。

## 里面有什么

| 文件 | 是什么 |
|---|---|
| `jiaoban/SKILL.md` | 给 agent 看的规则：选哪种压缩方式、开工、干活中、怎么写交接、离职、给别的模型派活 |
| `jiaoban/references/paper.md` | 论文的数字和出处 |
| `jiaoban/scripts/jiaoban.py` | 命令行工具，只用 Python 标准库：`init`、`brief`、`open`、`close`、`resign`、`sweep`、`snapshot` |

结构管得住的地方交给工具：`jiaoban close` 检查交接的必填字段齐全、改过的文件都已提交、项目的收工检查通过，不过就不让交班。

交接的必填字段：工号、事、任务原文、结论、改了哪些文件、怎么验的、走不通的、没做完的、下一步、完成标准。

## 怎么用

```bash
git clone https://github.com/chaoRookie/jiaoban.git
```

```bash
cp -R jiaoban/jiaoban ~/.claude/skills/
```

```bash
mkdir -p ~/.claude/bin && printf '#!/bin/sh\nexec python3 ~/.claude/skills/jiaoban/scripts/jiaoban.py "$@"\n' > ~/.claude/bin/jiaoban && chmod +x ~/.claude/bin/jiaoban
```

在项目里跑一次 `jiaoban init`，它会建好 `memory/` 和 `roles/`，并把交班规则写进 CLAUDE.md 或 AGENTS.md。之后在 Claude Code 里说「开工」「收工」「交班」就行。

## 许可证

[MIT](LICENSE)。论文的数字引自原文，版权归原作者。
