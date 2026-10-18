"""Read-only local Python import inventory; not a runtime package attestation."""

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str


@dataclass(frozen=True)
class ImportInventory:
    files: tuple[SourceFile, ...]
    dynamic_import_sites: tuple[str, ...]


def _local_module(root, dotted):
    if not dotted or any(not part.isidentifier() for part in dotted.split(".")):
        return None
    parts = dotted.split(".")
    base = root.joinpath(*parts)
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _package_parts(relative):
    parts = list(relative.with_suffix("").parts)
    return parts[:-1]


def _import_names(tree, relative):
    names = set()
    dynamic = []
    package = _package_parts(relative)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                names.update(".".join(parts[:index]) for index in range(1, len(parts) + 1))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(package) + 1:
                    dynamic.append(node.lineno)
                    continue
                base = package[:len(package) - node.level + 1]
                if node.module:
                    base.extend(node.module.split("."))
                name = ".".join(base)
            else:
                name = node.module or ""
            if name:
                parts = name.split(".")
                names.update(".".join(parts[:index]) for index in range(1, len(parts) + 1))
            for alias in node.names:
                if alias.name == "*":
                    dynamic.append(node.lineno)
                else:
                    names.add(f"{name}.{alias.name}" if name else alias.name)
        elif isinstance(node, ast.Call):
            function = node.func
            if ((isinstance(function, ast.Name) and function.id == "__import__")
                    or (isinstance(function, ast.Attribute)
                        and function.attr in {"import_module", "spec_from_file_location"})):
                literal = node.args[0] if node.args else None
                if (not isinstance(function, ast.Attribute)
                        or function.attr != "spec_from_file_location"):
                    if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                        parts = literal.value.split(".")
                        if all(part.isidentifier() for part in parts):
                            names.update(
                                ".".join(parts[:index])
                                for index in range(1, len(parts) + 1))
                            continue
                dynamic.append(node.lineno)
    return names, dynamic


def inventory_local_imports(root, entry, *, additional_modules=(), max_files=2000):
    """Over-approximate local imports without executing or modifying source."""
    root = Path(root).resolve(strict=True)
    entry = Path(entry)
    if not entry.is_absolute():
        entry = root / entry
    if not entry.is_relative_to(root) or entry.is_symlink():
        raise ValueError("entry must be a Python file under the root")
    entry = entry.resolve(strict=True)
    if not entry.is_relative_to(root) or entry.suffix != ".py":
        raise ValueError("entry must be a Python file under the root")
    pending = [entry]
    if type(additional_modules) not in (tuple, list):
        raise ValueError("additional modules must be explicit")
    for name in additional_modules:
        if type(name) is not str:
            raise ValueError("additional module name malformed")
        found = _local_module(root, name)
        if found is None:
            raise ValueError("additional module is unavailable")
        pending.append(found)
    seen = {}
    dynamic = set()
    while pending:
        path = pending.pop()
        relative = path.relative_to(root)
        key = relative.as_posix()
        if key in seen:
            continue
        if len(seen) >= max_files:
            raise ValueError("local import inventory exceeds file bound")
        if path.is_symlink() or not path.is_file():
            raise ValueError("local import path is not a regular file")
        source = path.read_bytes()
        tree = ast.parse(source, filename=key)
        seen[key] = hashlib.sha256(source).hexdigest()
        names, sites = _import_names(tree, relative)
        dynamic.update(f"{key}:{line}" for line in sites)
        for name in names:
            found = _local_module(root, name)
            if found is not None:
                if found.is_symlink() or not found.resolve().is_relative_to(root):
                    raise ValueError("local import escapes source root")
                pending.append(found)
    return ImportInventory(
        tuple(SourceFile(path, seen[path]) for path in sorted(seen)),
        tuple(sorted(dynamic)),
    )
