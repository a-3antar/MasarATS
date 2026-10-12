import ast
import io
import json
import sys
import tokenize
from pathlib import Path

STORE = Path("comments_store")
DOCS_EN = Path("docs_en")
SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "comments_store", "docs_en", "tools"}
KEEP_MARKERS = ("noqa", "type:", "pragma", "fmt:", "pylint", "isort")
MODULE = "<module>"


def py_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if not SKIP_DIRS & set(path.relative_to(root).parts):
            yield path


def read_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return lines


def find_docs(tree: ast.AST) -> dict:
    result = {}

    def register(node, qual):
        body = node.body
        first = body[0] if body else None
        is_doc = (
            isinstance(first, ast.Expr)
            and isinstance(getattr(first, "value", None), ast.Constant)
            and isinstance(first.value.value, str)
        )
        result[qual] = (node, first if is_doc else None)

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = prefix + child.name
                register(child, qual)
                walk(child, qual + ".")
            else:
                walk(child, prefix)

    register(tree, MODULE)
    walk(tree, "")
    return result


def set_docstring(lines: list[str], qual: str, raw: list[str] | None = None, text: str | None = None) -> bool:
    entry = find_docs(ast.parse("".join(lines))).get(qual)
    if entry is None:
        return False
    node, doc = entry
    first = node.body[0] if node.body else None
    indent_cols = doc.col_offset if doc else (first.col_offset if first and qual != MODULE else 0)
    new = raw if raw is not None else [f'{" " * indent_cols}"""{text}"""\n']

    if doc:
        lines[doc.lineno - 1:doc.end_lineno] = new
    elif isinstance(first, ast.Pass) and len(node.body) == 1:
        lines[first.lineno - 1:first.end_lineno] = new
    elif first is not None:
        start = min([first.lineno] + [d.lineno for d in getattr(first, "decorator_list", [])])
        lines[start - 1:start - 1] = new
    else:
        return False
    return True


def strip_file(path: Path, rel: Path, docs_en: dict) -> str:
    src = path.read_text(encoding="utf-8")
    lines = read_lines(path)
    docs = find_docs(ast.parse(src))

    drop, replace, stored_docs = set(), {}, {}
    for qual, (node, doc) in docs.items():
        if doc is None:
            continue
        start, end = doc.lineno - 1, doc.end_lineno
        stored_docs[qual] = lines[start:end]
        drop.update(range(start, end))
        indent = " " * doc.col_offset
        if qual in docs_en:
            replace[start] = f'{indent}"""{docs_en[qual]}"""\n'
        elif len(node.body) == 1:
            replace[start] = f"{indent}pass\n"
        drop.discard(start) if start in replace else None

    standalone, trailing = {}, {}
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.COMMENT or any(m in tok.string for m in KEEP_MARKERS):
            continue
        row, col = tok.start
        if row == 1 and tok.string.startswith(("#!", "# -*-")):
            continue
        line = lines[row - 1]
        if line[:col].strip() == "":
            standalone[row] = line.rstrip("\n")
        else:
            code = line[:col].rstrip()
            trailing[row] = (code, line[len(code):col] + tok.string)

    out, attach, pending = [], [], []
    for i, line in enumerate(lines):
        row = i + 1
        if i in drop:
            continue
        if i in replace:
            line = replace[i]
        if row in standalone:
            pending.append(standalone[row])
            continue
        if row in trailing:
            code, comment = trailing[row]
            attach.append((len(out), "e", comment))
            line = code + "\n"
        if pending and line.strip():
            attach.extend((len(out), "s", raw) for raw in pending)
            pending = []
        out.append(line)

    seen, occurrence = {}, []
    for line in out:
        key = line.strip()
        occurrence.append(seen.get(key, 0))
        seen[key] = seen.get(key, 0) + 1

    comments = [
        {"a": out[idx].strip(), "o": occurrence[idx], "t": kind, "c": text}
        for idx, kind, text in attach
    ]
    new_src = "".join(out)
    ast.parse(new_src)
    store_path = STORE / rel.with_suffix(".json")
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps({"docstrings": stored_docs, "comments": comments}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return new_src


def restore_file(path: Path, data: dict) -> str:
    lines = read_lines(path)
    positions: dict[tuple, list[int]] = {}
    for idx, line in enumerate(lines):
        positions.setdefault(line.strip(), []).append(idx)

    work = []
    for entry in data["comments"]:
        slots = positions.get(entry["a"], [])
        if entry["o"] >= len(slots):
            print(f"  ! anchor not found: {entry['a'][:50]!r}")
            continue
        work.append((slots[entry["o"]], entry))

    for idx, entry in sorted(work, key=lambda w: w[0], reverse=True):
        if entry["t"] == "e":
            lines[idx] = lines[idx].rstrip("\n") + entry["c"] + "\n"
    for idx, entry in sorted((w for w in work if w[1]["t"] == "s"), key=lambda w: w[0], reverse=True):
        lines[idx:idx] = [entry["c"] + "\n"]

    for qual, raw in data["docstrings"].items():
        if not set_docstring(lines, qual, raw=raw):
            print(f"  ! docstring target not found: {qual}")
    new_src = "".join(lines)
    ast.parse(new_src)
    return new_src


def cmd_strip(root: Path, force: bool) -> None:
    for path in py_files(root):
        rel = path.relative_to(root)
        if (STORE / rel.with_suffix(".json")).exists() and not force:
            print(f"skip (already stripped): {rel}")
            continue
        docs_path = DOCS_EN / rel.with_suffix(".json")
        docs_en = json.loads(docs_path.read_text(encoding="utf-8")) if docs_path.exists() else {}
        try:
            path.write_text(strip_file(path, rel, docs_en), encoding="utf-8")
            print(f"stripped: {rel}")
        except Exception as exc:
            print(f"FAILED {rel}: {exc}")


def cmd_restore(root: Path) -> None:
    for store_path in sorted(STORE.rglob("*.json")):
        rel = store_path.relative_to(STORE).with_suffix(".py")
        target = root / rel
        if not target.exists():
            continue
        try:
            data = json.loads(store_path.read_text(encoding="utf-8"))
            target.write_text(restore_file(target, data), encoding="utf-8")
            print(f"restored: {rel}")
        except Exception as exc:
            print(f"FAILED {rel}: {exc}")


def cmd_adddocs(root: Path) -> None:
    for docs_path in sorted(DOCS_EN.rglob("*.json")):
        rel = docs_path.relative_to(DOCS_EN).with_suffix(".py")
        target = root / rel
        if not target.exists():
            continue
        lines = read_lines(target)
        for qual, text in json.loads(docs_path.read_text(encoding="utf-8")).items():
            if not set_docstring(lines, qual, text=text):
                print(f"  ! not found in {rel}: {qual}")
        new_src = "".join(lines)
        ast.parse(new_src)
        target.write_text(new_src, encoding="utf-8")
        print(f"docs added: {rel}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    project_root = Path(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else Path(".")
    if command == "strip":
        cmd_strip(project_root, "--force" in sys.argv)
    elif command == "restore":
        cmd_restore(project_root)
    elif command == "adddocs":
        cmd_adddocs(project_root)
    else:
        print("usage: python tools/comment_tool.py [strip|adddocs|restore] [root] [--force]")