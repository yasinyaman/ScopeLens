"""Plugin CLI: `python -m etki.plugin <list|verify|install|sync|remove> …`

    python -m etki.plugin list [--json]                    # installed + state + stamp
    python -m etki.plugin verify <dist> [--report f]       # conformance (AdapterBench)
    python -m etki.plugin install git+URL@TAG              # community path (policy-gated)
    python -m etki.plugin install ./x.whl --sha256 HASH    # offline path (hash mandatory)
    python -m etki.plugin sync                             # exact reinstall from lockfile
    python -m etki.plugin remove <dist>

Faz 5 adds: search / verified install / mirror.
"""

from __future__ import annotations

import argparse
import json

from etki.adapters.plugins import get_plugin_registry
from etki.plugin import installer, policy
from etki.plugin.index_schema import IndexPlugin, IndexVersion
from etki.plugin.lockfile import LOCKFILE_NAME
from etki_api import PluginManifest

_EXIT_POLICY = 3  # policy refusal (distinct from install errors → scriptable)


def _cmd_list(as_json: bool) -> int:
    registry = get_plugin_registry()
    statuses = registry.statuses()
    if as_json:
        print(
            json.dumps(
                {
                    "plugins": [
                        {
                            "name": s.name,
                            "version": s.version,
                            "source": s.source,
                            "ports": s.ports,
                            "api_compat": s.api_compat,
                            "state": s.state,
                            "error": s.error,
                            "commit": s.commit,
                        }
                        for s in statuses
                    ],
                    "stamp": registry.stamp(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if not statuses:
        print("Kurulu plugin yok (entry-point grubu: etki.adapters).")
        return 0
    for s in statuses:
        marker = "✓" if s.state == "active" else "✗"
        detail = f"  — {s.error}" if s.error else ""
        ports = ", ".join(s.ports) or "-"
        print(f"{marker} {s.name} {s.version}  [{s.state}]  portlar: {ports}{detail}")
    print(f"audit damgası: {registry.stamp() or '[]'}")
    return 0


def _confirm(manifest: PluginManifest | None, source_desc: str, yes: bool) -> bool:
    """Capability confirmation — data comes from the STATIC manifest (no plugin
    code was imported to render this)."""
    print(f"Kaynak: {source_desc}")
    if manifest is None:
        print(
            "UYARI: pakette etki-plugin.toml yok — yetenek beyanı görüntülenemiyor. "
            "Plugin sözleşme/talep verinize adaptör olarak erişebilir."
        )
    else:
        caps = manifest.capabilities
        declared = []
        if caps.network:
            declared.append("ağ erişimi")
        declared.append(f"dosya sistemi: {caps.filesystem}")
        if caps.endpoints:
            declared.append(f"dış uçlar: {', '.join(caps.endpoints)}")
        print(f"Plugin: {manifest.name}  (etki-api aralığı: {manifest.api_compat})")
        print(f"Bildirdiği yetenekler: {'; '.join(declared)}")
        if caps.notes:
            print(f"Not: {caps.notes}")
    print("Bu plugin doğrulanmamış (verified değil). Sözleşme verinize erişebilir.")
    if yes:
        return True
    answer = input("Devam? [y/N] ").strip().lower()
    return answer in ("y", "yes", "e", "evet")


def _cmd_install(args: argparse.Namespace) -> int:
    target: str = args.target
    if target.startswith("git+"):
        if not policy.allows("git"):
            print(policy.refusal_message("git"))
            return _EXIT_POLICY
        raw = target[len("git+") :]
        if "@" not in raw:
            print("git kurulumu için ref zorunlu: git+URL@TAG (veya @COMMIT).")
            return 2
        url, ref = raw.rsplit("@", 1)
        try:
            commit = installer.resolve_git_ref(url, ref)
            import tempfile

            with tempfile.TemporaryDirectory(prefix="etki-plugin-") as tmp:
                manifest = installer.fetch_manifest_from_git(url, commit, tmp)
            if not _confirm(manifest, f"{url} @ {ref} (çözümlenen commit {commit[:12]})", args.yes):
                print("Vazgeçildi — hiçbir şey kurulmadı.")
                return 1
            entry = installer.install_git(
                url, ref, python=args.python, lockfile_path=args.lockfile, manifest=manifest
            )
        except installer.InstallError as exc:
            print(f"kurulum hatası: {exc}")
            return 1
        print(f"kuruldu: {entry.name} @ {entry.commit[:12]} → {args.lockfile}")
        return 0
    if target.endswith(".whl"):
        if not policy.allows("local"):
            print(policy.refusal_message("local"))
            return _EXIT_POLICY
        if not args.sha256:
            print("yerel wheel kurulumu için --sha256 zorunlu (air-gapped bütünlük kuralı).")
            return 2
        from pathlib import Path

        try:
            wheel_manifest = installer.read_manifest_from_wheel(Path(target))
            if not _confirm(wheel_manifest, target, args.yes):
                print("Vazgeçildi — hiçbir şey kurulmadı.")
                return 1
            entry = installer.install_wheel(
                target, sha256=args.sha256, python=args.python, lockfile_path=args.lockfile
            )
        except installer.InstallError as exc:
            print(f"kurulum hatası: {exc}")
            return 1
        print(f"kuruldu: {entry.name} (sha256 doğrulandı) → {args.lockfile}")
        return 0
    # Verified marketplace path — allowed under verified_only (that's its point).
    from etki.plugin import marketplace

    # --index overrides; otherwise the trust root: ETKI_PLUGIN_INDEX_URL env,
    # falling back to the official index URL (same resolution as the UI).
    source = args.index or marketplace.index_source()
    print(f"İndeks kaynağı: {source}")

    def _confirm_verified(plugin: IndexPlugin, version: IndexVersion) -> bool:
        caps = plugin.capabilities
        declared = []
        if caps.network:
            declared.append("ağ erişimi")
        declared.append(f"dosya sistemi: {caps.filesystem}")
        if caps.endpoints:
            declared.append(f"dış uçlar: {', '.join(caps.endpoints)}")
        print(f"Plugin: {plugin.name} {version.version}  (etki-api aralığı: {version.api_compat})")
        print(f"Bildirdiği yetenekler: {'; '.join(declared)}")
        print("Kaynak: DOĞRULANMIŞ marketplace index'i (imza + hash zinciri).")
        answer = input("Devam? [y/N] ").strip().lower()
        return answer in ("y", "yes", "e", "evet")

    try:
        entry = marketplace.install_verified(
            target,
            source,
            yes=args.yes,
            confirm=_confirm_verified,
            python=args.python,
            lockfile_path=args.lockfile,
        )
    except installer.InstallError as exc:
        print(f"kurulum hatası: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 — imza/ağ hataları da tek satır mesajdır
        print(f"kurulum hatası: {exc}")
        return 1
    print(f"kuruldu (verified): {entry.name} → {args.lockfile}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etki.plugin", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="kurulu plugin'leri ve durumlarını listele")
    p_list.add_argument("--json", action="store_true", help="makine-okunur çıktı")

    p_verify = sub.add_parser(
        "verify", help="bir plugin'i port sözleşmelerine karşı doğrula (conformance)"
    )
    p_verify.add_argument("dist", help="dağıtım adı, örn. etki-plugin-linear")
    p_verify.add_argument("--report", default=None, help="JSON rapor çıktı yolu")

    p_install = sub.add_parser(
        "install", help="plugin kur (git+URL@TAG | ./dosya.whl | <ad> --index …)"
    )
    p_install.add_argument("target")
    p_install.add_argument("--sha256", default=None, help="wheel kurulumunda ZORUNLU")
    p_install.add_argument(
        "--index",
        default=None,
        help="verified kurulum: index URL'i ya da mirror dizini "
        "(varsayılan: ETKI_PLUGIN_INDEX_URL ortam değişkeni, o da yoksa resmi index)",
    )
    p_install.add_argument("--yes", action="store_true", help="onay ekranını geç")
    p_install.add_argument("--python", default=None, help="hedef venv (test/CI)")
    p_install.add_argument("--lockfile", default=LOCKFILE_NAME)

    p_search = sub.add_parser("search", help="marketplace index'inde ara")
    p_search.add_argument("term")
    p_search.add_argument(
        "--index",
        default=None,
        help="index URL'i ya da mirror dizini "
        "(varsayılan: ETKI_PLUGIN_INDEX_URL ortam değişkeni, o da yoksa resmi index)",
    )

    p_mirror = sub.add_parser(
        "mirror", help="index + artifact'leri offline mirror'a indir (imza BURADA doğrulanır)"
    )
    p_mirror.add_argument("url", help="index.json URL'i")
    p_mirror.add_argument("dest", help="hedef dizin")

    p_sync = sub.add_parser("sync", help="lockfile'dan birebir yeniden kurulum")
    p_sync.add_argument("--python", default=None)
    p_sync.add_argument("--lockfile", default=LOCKFILE_NAME)

    p_remove = sub.add_parser("remove", help="plugin'i kaldır + lockfile'dan düş")
    p_remove.add_argument("dist")
    p_remove.add_argument("--python", default=None)
    p_remove.add_argument("--lockfile", default=LOCKFILE_NAME)

    args = parser.parse_args(argv)
    if args.command == "list":
        return _cmd_list(args.json)
    if args.command == "verify":
        # Thin delegate: the suite lives in etki-api so a plugin's own CI can run
        # it with only `etki-api[conformance]` installed.
        from etki_api.conformance.runner import run as conformance_run

        return conformance_run(args.dist, args.report)
    if args.command == "install":
        return _cmd_install(args)
    if args.command == "search":
        from etki.plugin import marketplace

        source = args.index or marketplace.index_source()
        print(f"İndeks kaynağı: {source}")
        try:
            index, _ = marketplace.load_index(source)
        except Exception as exc:  # noqa: BLE001 — CLI boundary
            print(f"index okunamadı: {exc}")
            return 1
        hits = marketplace.search(index, args.term)
        if not hits:
            print("Eşleşme yok.")
            return 1
        for p in hits:
            latest = max((v.version for v in p.versions), default="-")
            print(f"{p.name}  {latest}  portlar: {', '.join(p.ports) or '-'}  {p.summary}")
        return 0
    if args.command == "mirror":
        from etki.plugin import marketplace

        try:
            mirrored = marketplace.mirror(args.url, args.dest)
        except Exception as exc:  # noqa: BLE001
            print(f"mirror hatası: {exc}")
            return 1
        print(f"mirror tamam ({len(mirrored)} artifact, imza doğrulandı): {args.dest}")
        return 0
    if args.command == "sync":
        try:
            names = installer.sync(python=args.python, lockfile_path=args.lockfile)
        except installer.InstallError as exc:
            print(f"sync hatası: {exc}")
            return 1
        print(f"sync tamam: {names or 'lockfile boş'}")
        return 0
    if args.command == "remove":
        try:
            if not installer.remove(args.dist, python=args.python, lockfile_path=args.lockfile):
                print(f"{args.dist} lockfile'da yok.")
                return 1
        except installer.InstallError as exc:
            print(f"remove hatası: {exc}")
            return 1
        print(f"kaldırıldı: {args.dist}")
        return 0
    return 2  # unreachable — argparse enforces the subcommand set


if __name__ == "__main__":
    raise SystemExit(main())
