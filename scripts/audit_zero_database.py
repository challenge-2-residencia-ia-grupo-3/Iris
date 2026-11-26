#!/usr/bin/env python3
"""Auditoria automatizada de conformidade Zero-Student-Database (Issue #35 / RNF-01 / ADR-10).

Inspeciona o repositório (dependências, AST Python, SQL/DDL, docker-compose e frontend)
para certificar que:
1. Não existem modelos ORM nem tabelas de cadastro/perfis de alunos no backend;
2. As rotas FastAPI, parsers, exportadores e agentes não emitem cookies de sessão HTTP nem
   gravam arquivos temporários/documentos em disco em tempo de execução;
3. A persistência SQL no backend restringe-se exclusivamente à base vetorial científica do RAG
   (`iris_trechos`) e ao módulo isolado de histórico docente sanitizado (`backend/src/iris/storage/`,
   schema `docente.*`), sem dados de estudantes.
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Dependências e imports proibidos no backend de produção (ORMs, migrações e bancos de aplicação)
FORBIDDEN_ORM_PACKAGES = {
    "sqlalchemy",
    "sqlmodel",
    "peewee",
    "tortoise",
    "tortoise-orm",
    "alembic",
    "django",
    "sqlite3",
    "aiosqlite",
    "pymongo",
    "tinydb",
    "shelve",
    "dbm",
    "databases",
    "asyncpg",
    "pymysql",
    "mysql",
}

FORBIDDEN_ORM_BASES = {
    "DeclarativeBase",
    "SQLModel",
    "BaseModelORM",
}

FORBIDDEN_ORM_CALLS = {
    "declarative_base",
    "mapped_column",
    "Column",
    "create_engine",
    "sessionmaker",
}

FORBIDDEN_RUNTIME_IMPORTS = FORBIDDEN_ORM_PACKAGES | {"tempfile"}
FORBIDDEN_WRITE_CALLS = {
    "write_text",
    "write_bytes",
    "mkdtemp",
    "mkstemp",
    "NamedTemporaryFile",
    "TemporaryDirectory",
    "TemporaryFile",
    "to_sql",
}

# Diretórios do backend que atendem requisições de usuários em tempo de execução
RUNTIME_BACKEND_DIRS = (
    "api",
    "agents",
    "audio",
    "core",
    "exportacao",
    "parsers",
    "rag",
    "schemas",
    "security",
    "sessao",
)

# Termos de tabelas/entidades de cadastro de estudantes proibidos em SQL/DDL
FORBIDDEN_STUDENT_TABLE_RE = re.compile(
    r"\b(?:CREATE\s+TABLE|ALTER\s+TABLE|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b"
    r"[^\n;]*\b(?:alunos?|estudantes?|students?|cadastros?|usuarios?|laudos?|prontuarios?|perfis_alunos?)\b",
    re.IGNORECASE,
)

SQL_WRITE_RE = re.compile(
    r"\b(?:CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|INSERT\s+INTO|TRUNCATE|DELETE\s+FROM|COPY\s+\w+\s+FROM)\b",
    re.IGNORECASE,
)


@dataclass
class AuditResult:
    """Resultado consolidado da auditoria Zero-Database."""

    violations: list[str] = field(default_factory=list)
    checks_passed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.violations) == 0


def _normalize_pkg_name(spec: str) -> str:
    return re.split(r"[<>=!~;\[\s]", spec.strip(), maxsplit=1)[0].lower()


def _audit_pyproject(repo_root: Path, result: AuditResult) -> None:
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.exists():
        result.violations.append("pyproject.toml não encontrado na raiz do repositório.")
        return

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    deps: list[str] = list(data.get("project", {}).get("dependencies", []))
    for group_deps in data.get("dependency-groups", {}).values():
        if isinstance(group_deps, list):
            deps.extend(group_deps)

    encontrados = sorted(
        {
            _normalize_pkg_name(dep)
            for dep in deps
            if _normalize_pkg_name(dep) in FORBIDDEN_ORM_PACKAGES
        }
    )
    if encontrados:
        result.violations.append(
            f"Dependência(s) de ORM/banco de aplicação proibida(s) em pyproject.toml: {encontrados}"
        )
    else:
        result.checks_passed.append("pyproject.toml livre de dependências ORM/bancos de estudantes")


def _open_call_has_write_mode(node: ast.Call) -> bool:
    """Detecta chamadas `open(path, 'w'/'a'/'x'/'+')` ou `Path.open('w')`."""
    func = node.func
    is_builtin_open = isinstance(func, ast.Name) and func.id == "open"
    is_method_open = isinstance(func, ast.Attribute) and func.attr == "open"
    if not (is_builtin_open or is_method_open):
        return False

    # Segundo argumento posicional ou keyword `mode`
    mode_node: ast.AST | None = None
    if len(node.args) >= 2:
        mode_node = node.args[1]
    else:
        for kw in node.keywords:
            if kw.arg == "mode":
                mode_node = kw.value
                break

    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return any(ch in mode_node.value for ch in ("w", "a", "x", "+"))
    return False


def _audit_backend_python_ast(repo_root: Path, result: AuditResult) -> None:
    iris_pkg = repo_root / "backend" / "src" / "iris"
    if not iris_pkg.is_dir():
        result.violations.append("Pacote backend/src/iris não encontrado.")
        return

    all_py = sorted(iris_pkg.rglob("*.py"))
    runtime_files: list[Path] = []
    for path in all_py:
        rel = path.relative_to(iris_pkg)
        if len(rel.parts) == 1 or rel.parts[0] in RUNTIME_BACKEND_DIRS:
            runtime_files.append(path)

    for path in all_py:
        rel_str = str(path.relative_to(repo_root))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_str)

        for node in ast.walk(tree):
            # 1. Imports de ORM ou bancos de aplicação em todo `src/iris`
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0].lower()
                    if root_mod in FORBIDDEN_ORM_PACKAGES:
                        result.violations.append(f"{rel_str}:{node.lineno}: import ORM/DB proibido '{alias.name}'")
                    if path in runtime_files and root_mod in FORBIDDEN_RUNTIME_IMPORTS:
                        result.violations.append(
                            f"{rel_str}:{node.lineno}: import de persistência proibido em runtime '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_mod = node.module.split(".")[0].lower()
                if root_mod in FORBIDDEN_ORM_PACKAGES:
                    result.violations.append(f"{rel_str}:{node.lineno}: import ORM/DB proibido '{node.module}'")
                if path in runtime_files and root_mod in FORBIDDEN_RUNTIME_IMPORTS:
                    result.violations.append(
                        f"{rel_str}:{node.lineno}: import de persistência proibido em runtime '{node.module}'"
                    )
                for alias in node.names:
                    if alias.name == "SessionMiddleware":
                        result.violations.append(
                            f"{rel_str}:{node.lineno}: SessionMiddleware proibido em arquitetura stateless"
                        )

            # 2. Definições de classes ORM (`__tablename__`, herança de DeclarativeBase/SQLModel)
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                    if base_name in FORBIDDEN_ORM_BASES:
                        result.violations.append(
                            f"{rel_str}:{node.lineno}: classe ORM '{node.name}({base_name})' proibida"
                        )
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name) and target.id == "__tablename__":
                                result.violations.append(
                                    f"{rel_str}:{stmt.lineno}: atributo ORM '__tablename__' proibido"
                                )

            # 3. Chamadas de ORM, escrita em disco em runtime ou emissão de cookies
            elif isinstance(node, ast.Call):
                fn_name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else ""
                )
                if fn_name in FORBIDDEN_ORM_CALLS:
                    result.violations.append(f"{rel_str}:{node.lineno}: chamada ORM proibida '{fn_name}()'")
                if path in runtime_files:
                    if fn_name in FORBIDDEN_WRITE_CALLS or _open_call_has_write_mode(node):
                        result.violations.append(
                            f"{rel_str}:{node.lineno}: escrita em disco proibida em módulo de runtime ({fn_name})"
                        )
                    if fn_name in {"set_cookie", "SessionMiddleware"}:
                        result.violations.append(
                            f"{rel_str}:{node.lineno}: estado de sessão HTTP proibido ({fn_name})"
                        )

    result.checks_passed.append(
        f"AST do backend ({len(all_py)} arquivos em backend/src/iris) sem modelos ORM, cookies ou escrita em runtime"
    )


def _is_inside_dir(path: Path, parent_dir: Path) -> bool:
    try:
        path.resolve().relative_to(parent_dir.resolve())
        return True
    except ValueError:
        return False


def _audit_sql_and_vector_store(repo_root: Path, result: AuditResult) -> None:
    allowed_teacher_storage_dir = (repo_root / "backend" / "src" / "iris" / "storage").resolve()

    sql_files = list((repo_root / "backend").rglob("*.sql")) + list((repo_root / "rag").rglob("*.sql"))
    if sql_files:
        for sql_file in sql_files:
            txt = sql_file.read_text(encoding="utf-8")
            in_teacher_storage = _is_inside_dir(sql_file, allowed_teacher_storage_dir)
            if FORBIDDEN_STUDENT_TABLE_RE.search(txt):
                result.violations.append(
                    f"SQL de tabela de estudantes proibido detectado em {sql_file.relative_to(repo_root)}"
                )
            elif in_teacher_storage:
                if "docente." not in txt:
                    result.violations.append(
                        f"Arquivo SQL em storage/ deve operar explicitamente no schema 'docente.': {sql_file.relative_to(repo_root)}"
                    )
            elif "iris_trechos" not in txt:
                result.violations.append(
                    f"Arquivo SQL não autorizado fora do corpus RAG/storage docente: {sql_file.relative_to(repo_root)}"
                )

    # Verifica todos os .py de backend/ e rag/iris-rag/pacote/ contra DDL de tabelas de alunos
    py_targets = list((repo_root / "backend" / "src").rglob("*.py")) + list(
        (repo_root / "rag" / "iris-rag" / "pacote").glob("*.py")
    )
    allowed_ddl_file = repo_root / "rag" / "iris-rag" / "pacote" / "banco_pg.py"

    for py_file in py_targets:
        text = py_file.read_text(encoding="utf-8")
        rel = py_file.relative_to(repo_root)
        if FORBIDDEN_STUDENT_TABLE_RE.search(text):
            result.violations.append(f"SQL de tabela de estudantes proibido detectado em {rel}")
        in_allowed_sql_location = (
            py_file.resolve() == allowed_ddl_file.resolve()
            or _is_inside_dir(py_file, allowed_teacher_storage_dir)
        )
        if not in_allowed_sql_location and SQL_WRITE_RE.search(text):
            result.violations.append(
                f"Comando SQL de escrita/DDL fora de banco_pg.py ou iris/storage/ detectado em {rel}"
            )

    # Garante que banco_pg.py define apenas a tabela científica `iris_trechos`
    if allowed_ddl_file.exists():
        banco_txt = allowed_ddl_file.read_text(encoding="utf-8")
        if 'TABELA = "iris_trechos"' not in banco_txt:
            result.violations.append("banco_pg.py deve restringir a persistência à tabela 'iris_trechos'.")

    # Garante que docker-compose.yml possui apenas pgvector e ollama (sem serviço de banco de alunos)
    compose_path = repo_root / "docker-compose.yml"
    if compose_path.exists():
        compose_txt = compose_path.read_text(encoding="utf-8")
        if re.search(r"^\s{2}(?:alunos|students|students_db)\s*:", compose_txt, re.MULTILINE):
            result.violations.append("docker-compose.yml contém serviço de banco de estudantes não autorizado.")

    result.checks_passed.append(
        "Persistência SQL restrita exclusivamente ao corpus RAG ('iris_trechos') e schema docente ('docente.*')"
    )


def _audit_config_and_frontend(repo_root: Path, result: AuditResult) -> None:
    config_path = repo_root / "backend" / "src" / "iris" / "config.py"
    if config_path.exists():
        cfg_txt = config_path.read_text(encoding="utf-8")
        if "zero_student_database: bool = True" not in cfg_txt or "stateless_mode: bool = True" not in cfg_txt:
            result.violations.append("config.py deve declarar zero_student_database=True e stateless_mode=True.")
    else:
        result.violations.append("backend/src/iris/config.py não encontrado.")

    # Garante que o frontend não envia nem persiste nome de aluno ou dados clínicos em storage
    storage_file = repo_root / "frontend" / "src" / "services" / "portableProfileStorage.ts"
    if storage_file.exists():
        st_txt = storage_file.read_text(encoding="utf-8")
        if "FORBIDDEN_PERSONAL_OR_CLINICAL_KEYS" not in st_txt or "sanitizarPerfilParaLocalStorage" not in st_txt:
            result.violations.append(
                "portableProfileStorage.ts deve validar e bloquear campos pessoais/clínicos antes de gravar em localStorage."
            )

    result.checks_passed.append("Configuração backend e contrato anônimo do frontend em conformidade com RNF-01")


def run_audit(repo_root: Path | None = None) -> AuditResult:
    """Executa todas as verificações de auditoria Zero-Database no repositório."""
    root = (repo_root or REPO_ROOT).resolve()
    result = AuditResult()
    _audit_pyproject(root, result)
    _audit_backend_python_ast(root, result)
    _audit_sql_and_vector_store(root, result)
    _audit_config_and_frontend(root, result)
    return result


def main() -> int:
    result = run_audit()
    print("=== Auditoria Zero-Database & Arquitetura Stateless (Issue #35 / RNF-01) ===")
    for item in result.checks_passed:
        print(f"  [OK]    {item}")
    for err in result.violations:
        print(f"  [FALHA] {err}", file=sys.stderr)

    if not result.ok:
        print(f"\nAuditoria reprovada com {len(result.violations)} violação(ões).", file=sys.stderr)
        return 1

    print("\nAuditoria concluída com sucesso: 0 modelos ORM ou tabelas de estudantes encontrados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
