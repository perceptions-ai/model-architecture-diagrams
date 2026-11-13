#!/usr/bin/env python3
"""Static Python inventory; never import or execute the analyzed repository."""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path


class Source:
    def __init__(self, root, revision=None):
        self.root = Path(root).resolve()
        self.revision = self.git('rev-parse', '--verify', revision + '^{commit}').strip() if revision else None
        if not self.root.is_dir():
            raise ValueError('Source root does not exist')
        self.cache = {}

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL).decode()

    def read(self, path):
        p = Path(path)
        if p.is_absolute() or '..' in p.parts:
            raise ValueError('Source paths must be relative without ..: ' + path)
        if path not in self.cache:
            if self.revision:
                data = subprocess.check_output(['git', '-C', str(self.root), 'show', self.revision + ':' + path])
            else:
                resolved = (self.root / p).resolve()
                if resolved != self.root and self.root not in resolved.parents:
                    raise ValueError('Source escapes repository: ' + path)
                data = resolved.read_bytes()
            self.cache[path] = data
        return self.cache[path]

    def audit(self):
        try:
            head = self.git('rev-parse', 'HEAD').strip()
            dirty = bool(self.git('status', '--porcelain'))
        except subprocess.CalledProcessError:
            head, dirty = None, None
        return dict(root=str(self.root), mode='git-object' if self.revision else 'working-tree',
                    revision=self.revision, head=head, working_tree_dirty=dirty,
                    files=[dict(path=p, sha256=hashlib.sha256(b).hexdigest(), bytes=len(b))
                           for p, b in sorted(self.cache.items())])


def inventory(src):
    if src.revision:
        paths = src.git('ls-tree', '-r', '--name-only', src.revision).splitlines()
    else:
        try:
            paths = src.git('ls-files', '--cached', '--others', '--exclude-standard').splitlines()
        except subprocess.CalledProcessError:
            paths = [str(p.relative_to(src.root)) for p in src.root.rglob('*.py')
                     if not {'.git', '.venv', 'node_modules', '__pycache__'} & set(p.parts)]
    result = []
    for path in sorted(set(paths)):
        if not path.endswith('.py'):
            continue
        try:
            data = src.read(path)
            tree = ast.parse(data, filename=path)
            symbols = []
            def visit(node, prefix=''):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        name = prefix + child.name
                        symbols.append(dict(name=name, kind=type(child).__name__, line=child.lineno,
                                            end_line=child.end_lineno))
                        visit(child, name + '.')
                    else:
                        visit(child, prefix)
            visit(tree)
            source_text = data.decode('utf-8-sig')
            imports = [ast.get_source_segment(source_text, n) for n in ast.walk(tree)
                       if isinstance(n, (ast.Import, ast.ImportFrom))]
            result.append(dict(path=path, symbols=symbols, imports=imports))
        except (SyntaxError, OSError, UnicodeError, ValueError) as e:
            result.append(dict(path=path, error=str(e)))
    return dict(files=result, audit=src.audit(), note='Static inventory, not a call graph or shape proof.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--revision')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory(Source(args.repo, args.revision)), ensure_ascii=False, indent=2) + '\n')
    print(output)
