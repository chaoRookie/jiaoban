import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REQUIRED = ["工号", "事", "任务原文", "结论", "改了哪些文件", "怎么验的", "走不通的", "没做完的", "下一步", "完成标准"]
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")
BEGIN = "<!-- 交班规则 开始 -->"
END = "<!-- 交班规则 结束 -->"
PROTOCOL = f"""{BEGIN}
## 交班规则（会话即员工，随时可换）

这个项目里的每个会话都是一个随时可以换掉的员工。下一个会话要知道的东西都写进仓库，不留在聊天里。做法和论文依据见交班技能 `~/.claude/skills/jiaoban`。

开工：
1. 运行 `~/.claude/bin/jiaoban brief`（中文名 `交班`），读它打印的现状卡；领了岗位就加 `--role <工号>`，会把岗位卡一起打出来。
2. 要细节时按需去翻：grep、看一段、看某次提交，不把整份长文件或整段历史读进来。
3. 接一件事前运行 `jiaoban open <工号> <事>`，事只用小写英文、数字和横线。
4. 一个会话只做一件小事。

干活中：会话被自动压缩过一次，或者已经很长，先按收工的格式写一份交接，再接着做或换新会话。

收工：
1. 写交接 `memory/handoff/<日期>-<工号>-<事>.md`，开头是 YAML front matter，一个字段一行。必填：工号、事、任务原文（原话照抄）、结论（验证过的和猜的分开）、改了哪些文件、怎么验的、走不通的（没有就写「无」）、没做完的、下一步（第一条具体命令或改动）、完成标准。选填：肥肥交代的（这次说过的偏好和纠正）、去哪查（文件:行、提交号、命令）。交接写给下一个人用：只挑接着干要用的事实，不写经过。
2. 把改过的文件提交进 git。
3. 运行 `jiaoban close <工号> <事>`。它检查交接字段齐全、列出的文件已提交，通过后把这件事标成做完并提交 memory/。不通过就是没交接完。

离职（这个会话要被归档前）：运行 `jiaoban resign`。没提交的改动会自动保全到 `refs/keep/auto/<分支>`，没推到远程的 HEAD 留本地保全分支；还有该进项目的改动、或今天没写交接，就不通过，先别归档。

决定写进 `memory/decisions.md`（表格一行一条：日期、决定、谁定）。岗位卡在 `roles/<工号>.md`。
{END}
"""


def now():
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        return datetime.now()


def git(cwd, *a):
    try:
        r = subprocess.run(["git", "--no-optional-locks", *a], cwd=cwd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def is_repo(d):
    return git(d, "rev-parse", "--is-inside-work-tree")[1] == "true"


def find_root(start):
    d = Path(start).resolve()
    for p in [d, *d.parents]:
        if (p / "memory" / "work.json").exists() or (p / "memory" / "decisions.md").exists():
            return p
    return d


def load_work(root):
    p = root / "memory" / "work.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_work(root, w):
    p = root / "memory" / "work.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(w, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def parse_front(text):
    if not text.startswith("---"):
        return None
    parts = text.split("\n---", 1)
    if len(parts) < 2:
        return None
    out = {}
    for line in parts[0].splitlines()[1:]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        out[k.strip()] = v
    return out


def handoffs(root):
    d = root / "memory" / "handoff"
    return sorted(d.glob("*.md")) if d.exists() else []


def cmd_init(a):
    root = Path(a.dir).resolve()
    (root / "memory" / "handoff").mkdir(parents=True, exist_ok=True)
    (root / "roles").mkdir(exist_ok=True)
    dec = root / "memory" / "decisions.md"
    if not dec.exists():
        dec.write_text("# 决定\n\n| 日期 | 决定 | 谁定 |\n|---|---|---|\n", encoding="utf-8")
    if not (root / "memory" / "work.json").exists():
        save_work(root, {})
    targets = [p for p in (root / "CLAUDE.md", root / "AGENTS.md") if p.exists()] or [root / "CLAUDE.md"]
    for t in targets:
        s = t.read_text(encoding="utf-8") if t.exists() else ""
        if BEGIN in s:
            s = s[: s.index(BEGIN)] + PROTOCOL.strip() + s[s.index(END) + len(END):]
        else:
            s = (s.rstrip() + "\n\n" if s.strip() else "") + PROTOCOL
        t.write_text(s, encoding="utf-8")
    print(f"已在 {root} 建好 memory/、roles/，交班规则写进 {', '.join(t.name for t in targets)}")
    return 0


def cmd_brief(a):
    root = find_root(a.dir)
    print(f"# 现状卡：{root.name}")
    print(f"目录 {root}　北京时间 {now().strftime('%Y-%m-%d %H:%M')}")
    if is_repo(root):
        head = git(root, "log", "-1", "--format=%h %ci %s")[1]
        dirty = len([x for x in git(root, "status", "--porcelain")[1].splitlines() if x.strip()])
        print(f"git：{head}；未提交 {dirty} 个")
    else:
        print("git：这里还不是 git 仓库")
    print()
    if a.role:
        rc = root / "roles" / f"{a.role}.md"
        print(f"## 岗位卡 {a.role}")
        print(rc.read_text(encoding="utf-8").strip() if rc.exists() else f"没有 {rc.relative_to(root)}，先问总经理或肥肥。")
        print()
    w = load_work(root)
    opened = {k: v for k, v in w.items() if v.get("status") != "done"}
    print(f"## 进行中的事（{len(opened)}）")
    for k, v in opened.items():
        print(f"- {k}：{v.get('owner', '?')}，{v.get('opened_at', '?')} 开始" + (f"；{v['note']}" if v.get("note") else ""))
    if not opened:
        print("- 没有")
    print()
    dec = root / "memory" / "decisions.md"
    if dec.exists():
        rows = [l for l in dec.read_text(encoding="utf-8").splitlines() if l.startswith("|") and not l.startswith("|---") and "决定" not in l[:12]]
        print(f"## 最近的决定（共 {len(rows)} 条，列最后 8 条）")
        for l in rows[-8:]:
            print(l)
        print()
    hs = handoffs(root)
    print(f"## 最近的交接（共 {len(hs)} 份，列最后 3 份）")
    for h in hs[-3:]:
        fm = parse_front(h.read_text(encoding="utf-8")) or {}
        print(f"- {h.name}")
        for k in ("结论", "走不通的", "没做完的", "下一步"):
            if k in fm:
                v = fm[k]
                print(f"  {k}：{'；'.join(v) if isinstance(v, list) else v}")
    if not hs:
        print("- 还没有")
    print()
    extra = root / "memory" / "jiaoban.json"
    if extra.exists():
        cfg = json.loads(extra.read_text(encoding="utf-8"))
        for cmd in cfg.get("brief_extra", []):
            print(f"## {cmd.get('title', '项目自检')}")
            try:
                r = subprocess.run(cmd["run"], cwd=root, shell=True, capture_output=True, text=True, timeout=120)
                print((r.stdout or r.stderr).strip() or "（无输出）")
            except subprocess.TimeoutExpired:
                print("超时")
            print()
    ks = keeps(root)
    if ks:
        print(f"## 保全的工作（共 {len(ks)} 个，列最近 5 个；本卡只读，不会新建保全）")
        for ref, when, subj in ks[:5]:
            print(f"- {ref.replace('refs/heads/', '').replace('refs/', '')}　{when[:16]}　{subj[:60]}")
        print("看一个文件：git show <保全>:<文件>")
        print("只恢复离职时没提交的那批（不动别的文件）：git diff --name-only <保全>^ <保全> | xargs git checkout <保全> --")
        print("保全只在这台电脑的 .git 里，没推远程；要长期留就让肥肥决定推不推。")
        print()
    roles = sorted((root / "roles").glob("*.md")) if (root / "roles").exists() else []
    if roles and not a.role:
        print("## 岗位")
        print("、".join(r.stem for r in roles) + "（加 --role <工号> 看岗位卡）")
        print()
    print("收工：写交接 → 提交 → jiaoban close <工号> <事>")
    return 0


def after_change(root, event, worker, task):
    cfg_path = root / "memory" / "jiaoban.json"
    if not cfg_path.exists():
        return
    try:
        hooks = json.loads(cfg_path.read_text(encoding="utf-8")).get("after_change", [])
    except ValueError:
        return
    env = dict(os.environ, JIAOBAN_EVENT=event, JIAOBAN_WORKER=worker, JIAOBAN_TASK=task)
    for h in hooks:
        try:
            subprocess.run(h["run"], cwd=root, shell=True, capture_output=True, text=True, timeout=h.get("timeout", 60), env=env)
        except Exception:
            pass


def cmd_open(a):
    root = find_root(a.dir)
    if not SLUG.fullmatch(a.task):
        print("事只用小写英文、数字和横线")
        return 1
    w = load_work(root)
    if a.task in w and w[a.task].get("status") != "done":
        print(f"{a.task} 已经在进行中（{w[a.task].get('owner')}）")
        return 0
    w[a.task] = {"owner": a.worker, "status": "open", "opened_at": now().strftime("%Y-%m-%d"), "closed_at": None, "handoff": None}
    if a.note:
        w[a.task]["note"] = a.note
    save_work(root, w)
    print(f"已登记：{a.worker} 接了 {a.task}")
    after_change(root, "open", a.worker, a.task)
    return 0


def cmd_close(a):
    root = find_root(a.dir)
    problems = []
    cands = sorted((root / "memory" / "handoff").glob(f"*-{a.worker}-{a.task}.md")) if (root / "memory" / "handoff").exists() else []
    if not cands:
        print(f"没有交接文件 memory/handoff/<日期>-{a.worker}-{a.task}.md")
        return 1
    h = cands[-1]
    fm = parse_front(h.read_text(encoding="utf-8"))
    if fm is None:
        problems.append("交接文件开头没有 YAML front matter")
        fm = {}
    for k in REQUIRED:
        if k not in fm or fm[k] in ("", []):
            problems.append(f"交接缺字段：{k}")
    if fm.get("工号") and fm.get("工号") != a.worker:
        problems.append(f"交接里的工号是 {fm.get('工号')}，不是 {a.worker}")
    files = fm.get("改了哪些文件") or []
    files = files if isinstance(files, list) else [files]
    repo = is_repo(root)
    if repo:
        for f in files:
            if not (root / f).exists():
                continue
            if git(root, "ls-files", "--error-unmatch", f)[0] != 0:
                problems.append(f"没进 git：{f}")
            elif git(root, "status", "--porcelain", "--", f)[1]:
                problems.append(f"有改动没提交：{f}")
    cfg_path = root / "memory" / "jiaoban.json"
    if cfg_path.exists():
        for chk in json.loads(cfg_path.read_text(encoding="utf-8")).get("close_check", []):
            try:
                r = subprocess.run(chk["run"], cwd=root, shell=True, capture_output=True, text=True, timeout=chk.get("timeout", 900))
                if r.returncode != 0:
                    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
                    problems.append(f"收工检查「{chk.get('title', chk['run'])}」没过：" + " / ".join(tail))
            except subprocess.TimeoutExpired:
                problems.append(f"收工检查「{chk.get('title', chk['run'])}」超时")
    if problems:
        print("交接没通过：")
        for p in problems:
            print(f"- {p}")
        return 1
    w = load_work(root)
    item = w.get(a.task) or {"owner": a.worker, "opened_at": now().strftime("%Y-%m-%d")}
    item.update(status="done", closed_at=now().strftime("%Y-%m-%d"), handoff=str(h.relative_to(root)))
    w[a.task] = item
    save_work(root, w)
    if repo:
        git(root, "add", "memory")
        rc, _, err = git(root, "commit", "-q", "-m", f"{a.worker}: 交班 {a.task}")
        if rc != 0 and "nothing to commit" not in (err + _):
            print(f"交接通过，但 memory/ 没提交上：{err[-300:]}")
            return 1
    print(f"交接通过：{a.worker} 的 {a.task} 已标成做完" + ("，memory/ 已提交" if repo else "（不是 git 仓库，没提交）"))
    after_change(root, "close", a.worker, a.task)
    return 0


def keep_name(root):
    b = git(root, "branch", "--show-current")[1] or Path(root).name
    return re.sub(r"[^A-Za-z0-9._/-]+", "-", b).strip("-/") or "detached"


def snapshot(root, quiet=False):
    if not is_repo(root):
        return None
    top = git(root, "rev-parse", "--show-toplevel")[1]
    dirty = [l for l in git(top, "status", "--porcelain", "-uall")[1].splitlines() if l.strip()]
    if not dirty:
        return None
    import tempfile

    fd, idx = tempfile.mkstemp(prefix="jiaoban-idx-")
    os.close(fd)
    os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    try:
        def g(*a, inp=None):
            r = subprocess.run(["git", *a], cwd=top, capture_output=True, text=True, env=env, input=inp, timeout=120)
            return r.returncode, r.stdout.strip()

        if git(top, "rev-parse", "--verify", "HEAD")[0] == 0:
            g("read-tree", "HEAD")
        g("add", "-A")
        rc, tree = g("write-tree")
        if rc != 0:
            return None
        ref = f"refs/keep/auto/{keep_name(top)}"
        last = git(top, "rev-parse", "--verify", "-q", ref + "^{tree}")[1]
        if last == tree:
            return ref
        parents = ["-p", "HEAD"] if git(top, "rev-parse", "--verify", "HEAD")[0] == 0 else []
        msg = f"自动保全：{len(dirty)} 个未提交改动，{now().strftime('%Y-%m-%d %H:%M')} 北京时间\n"
        rc, c = g("-c", "user.name=jiaoban", "-c", "user.email=noreply@anthropic.com", "commit-tree", tree, *parents, inp=msg)
        if rc == 0 and c:
            git(top, "update-ref", "-m", "jiaoban snapshot", ref, c)
            if not quiet:
                print(f"已保全 {len(dirty)} 个未提交改动到 {ref}（{c[:8]}）")
            return ref
    finally:
        if os.path.exists(idx):
            os.unlink(idx)
    return None


def keeps(root):
    if not is_repo(root):
        return []
    out = git(root, "for-each-ref", "--sort=-committerdate", "--format=%(refname)|%(committerdate:iso)|%(subject)", "refs/keep", "refs/heads/keep")[1]
    return [l.split("|", 2) for l in out.splitlines() if l.strip()]


def cmd_snapshot(a):
    try:
        snapshot(Path(a.dir).resolve(), quiet=a.quiet)
    except Exception as e:
        if not a.quiet:
            print(f"保全没做成：{e}")
    return 0


def cmd_sweep(a):
    root = Path(a.dir).resolve()
    if not is_repo(root):
        print("不是 git 仓库")
        return 1
    paths = [l[9:] for l in git(root, "worktree", "list", "--porcelain")[1].splitlines() if l.startswith("worktree ")]
    for p in paths:
        n = len([l for l in git(p, "status", "--porcelain", "-uall")[1].splitlines() if l.strip()])
        ref = snapshot(Path(p), quiet=True) if n else None
        print(f"- {p}：未提交 {n} 个" + (f"，已保全到 {ref}" if ref else ""))
    return 0


def cmd_resign(a):
    root = Path(a.dir).resolve()
    if not is_repo(root):
        print("这里不是 git 仓库，没法检查；离职前把要留的东西拷到别处")
        return 1
    top = Path(git(root, "rev-parse", "--show-toplevel")[1])
    problems, notes = [], []
    ref = snapshot(top, quiet=True)
    dirty = [l for l in git(top, "status", "--porcelain", "-uall")[1].splitlines() if l.strip()]
    if dirty:
        msg = f"还有 {len(dirty)} 个未提交改动（已自动保全到 {ref}）"
        if a.keep_dirty:
            notes.append(msg + "；按 --keep-dirty 只留保全，不进项目")
        else:
            problems.append(msg + "。该进项目的先提交；确定只留保全的，加 --keep-dirty")
    head = git(top, "rev-parse", "--short", "HEAD")[1]
    remote = git(top, "branch", "-r", "--contains", "HEAD")[1]
    if remote:
        notes.append(f"HEAD {head} 已在远程：{remote.splitlines()[0].strip()}")
    else:
        kref = f"refs/heads/keep/{keep_name(top)}-{now().strftime('%Y%m%d')}"
        git(top, "update-ref", kref, "HEAD")
        notes.append(f"HEAD {head} 没在远程，已留本地保全分支 {kref.replace('refs/heads/', '')}")
    today = now().strftime("%Y-%m-%d")
    recent = []
    for pat in ("memory/handoff/*.md", "docs/handoff/sessions/*.md"):
        for f in top.glob(pat):
            if datetime.fromtimestamp(f.stat().st_mtime).astimezone(now().tzinfo).strftime("%Y-%m-%d") == today or f.name.startswith(today):
                recent.append(str(f.relative_to(top)))
    if recent:
        notes.append("今天的交接：" + "、".join(sorted(recent)[-3:]))
    else:
        problems.append("今天没有交接文件（memory/handoff/ 或 docs/handoff/sessions/）。先写交接再离职")
    print(f"# 离职检查：{top}")
    for n in notes:
        print(f"- {n}")
    if problems:
        print("没通过，先别归档：")
        for p in problems:
            print(f"- {p}")
        return 1
    print("通过：可以归档。接手的新会话在项目里跑 jiaoban brief，会看到保全分支和交接。")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jiaoban", description="会话即员工：开工打印现状卡，收工检查交接")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--dir", default=".")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("brief")
    p.add_argument("--dir", default=".")
    p.add_argument("--role")
    p.set_defaults(fn=cmd_brief)
    p = sub.add_parser("open")
    p.add_argument("worker")
    p.add_argument("task")
    p.add_argument("--note")
    p.add_argument("--dir", default=".")
    p.set_defaults(fn=cmd_open)
    p = sub.add_parser("close")
    p.add_argument("worker")
    p.add_argument("task")
    p.add_argument("--dir", default=".")
    p.set_defaults(fn=cmd_close)
    p = sub.add_parser("snapshot")
    p.add_argument("--dir", default=".")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(fn=cmd_snapshot)
    p = sub.add_parser("sweep")
    p.add_argument("--dir", default=".")
    p.set_defaults(fn=cmd_sweep)
    p = sub.add_parser("resign")
    p.add_argument("--dir", default=".")
    p.add_argument("--keep-dirty", action="store_true")
    p.set_defaults(fn=cmd_resign)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
