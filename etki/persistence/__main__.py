"""Schema creation + user management CLI.

- `python -m etki.persistence`                         → create schema
- `python -m etki.persistence create-user <name> <role> [--projects p1,p2]`
  → add a user (password prompted); --projects restricts accessible projects
"""

from __future__ import annotations

import getpass
import sys

from etki.auth import ROLES, build_user_store
from etki.config import Settings
from etki.persistence.db import init_schema, make_engine


def _create_user(args: list[str]) -> int:
    projects: list[str] = []
    positional: list[str] = []
    it = iter(args)
    for arg in it:
        if arg == "--projects":
            value = next(it, "")
            projects = [p.strip() for p in value.split(",") if p.strip()]
        elif arg.startswith("--projects="):
            projects = [p.strip() for p in arg.split("=", 1)[1].split(",") if p.strip()]
        else:
            positional.append(arg)
    if len(positional) < 2:
        print(
            "Kullanım: python -m etki.persistence create-user <kullanıcı> <rol> "
            "[--projects p1,p2]"
        )
        return 2
    username, role = positional[0], positional[1]
    if role not in ROLES:
        print(f"Geçersiz rol: {role} (geçerli: {', '.join(sorted(ROLES))})")
        return 2
    password = getpass.getpass("Parola: ")
    if password != getpass.getpass("Parola (tekrar): "):
        print("Parolalar eşleşmedi.")
        return 1
    store = build_user_store(Settings().db_url)
    try:
        store.create(username, password, role, projects=projects or None)
    except ValueError as exc:
        print(f"Hata: {exc}")
        return 1
    if projects:
        scope = ", ".join(projects)
    elif role == "pmo":
        scope = "tümü (ETKI_PMO_GLOBAL açıkken)"
    else:
        scope = "HİÇBİRİ — --projects ile izin verin"
    print(f"Kullanıcı oluşturuldu: {username} ({role}) — projeler: {scope}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "create-user":
        return _create_user(argv[1:])
    settings = Settings()
    init_schema(make_engine(settings.db_url))
    print(f"Şema oluşturuldu → {settings.db_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
