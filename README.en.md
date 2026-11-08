[中文](README.md) | **English**

# Jiaoban (handoff)

Every session is an employee who can be replaced at any time.

Sessions grow long, and long sessions are slower, costlier and more forgetful. This skill keeps the context short and writes what must be remembered into the repository, alongside git commits. A fresh session reads one handoff note and carries on.

## Backed by a paper

NVIDIA's "You don't need long context" ([arXiv 2611.05306](https://arxiv.org/abs/2611.05306)) tested Claude Opus 4.5 and GPT 5.6 Sol on 13 benchmarks:

| Finding | Numbers |
|---|---|
| Compacting long-horizon work into a state and starting a fresh conversation keeps accuracy | Opus −3.7 to +5.6 pp, GPT −3.3 to +4.4 pp; Opus on SWE-bench Verified went from 70.0 to 74.8 |
| Reading long inputs selectively beats loading them whole | Opus −0.4 to +40.0 pp, GPT +1.0 to +30.9 pp |
| One action per conversation does not collapse | Opus on SWE-bench Verified: 70.0 to 70.2 |
| Long context is expensive | Serving a 256K window instead of 16K costs 3.6x to 7x more per output token |
| The best compaction is a brief for what comes next, not a narrative | Appendix A: the verbatim task, current occupation, plan and completion criteria |

Every rule in the skill maps to a section of the paper. Numbers and page references are in [`jiaoban/references/paper.md`](jiaoban/references/paper.md) (Chinese).

## Contents

| File | What it is |
|---|---|
| `jiaoban/SKILL.md` | Rules for the agent (Chinese): which compaction regime to use, starting work, mid-session, writing a handoff, resigning, delegating to other models |
| `jiaoban/references/paper.md` | Numbers and sources from the paper |
| `jiaoban/scripts/jiaoban.py` | Standard-library Python CLI: `init`, `brief`, `open`, `close`, `resign`, `sweep`, `snapshot` |

What a tool can enforce, the tool enforces: `jiaoban close` refuses to close a task unless the handoff has every required field, the listed files are committed and the project's close checks pass.

## Install

```bash
git clone https://github.com/chaoRookie/jiaoban.git
```

```bash
cp -R jiaoban/jiaoban ~/.claude/skills/
```

```bash
mkdir -p ~/.claude/bin && printf '#!/bin/sh\nexec python3 ~/.claude/skills/jiaoban/scripts/jiaoban.py "$@"\n' > ~/.claude/bin/jiaoban && chmod +x ~/.claude/bin/jiaoban
```

Run `jiaoban init` once in a project. It creates `memory/` and `roles/` and writes the handoff rules into CLAUDE.md or AGENTS.md.

## License

[MIT](LICENSE). Figures quoted from the paper remain the authors'.
