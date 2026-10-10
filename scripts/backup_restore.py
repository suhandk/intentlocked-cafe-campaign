"""Freeze-runbook backup/restore: fresh targets only; no credentials or app feature."""

import argparse
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from backend.contracts import utc_now


def digest_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def integrity(database):
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not list(db.execute("PRAGMA foreign_key_check"))
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ["work_jobs", "generation_runs", "optimization_runs"]:
            if table in tables:
                assert not db.execute(
                    f"SELECT 1 FROM {table} WHERE status IN ('queued','running') LIMIT 1"
                ).fetchone(), "Stop work and shut down the server before backing up"
        return {
            table: db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in sorted(tables)
            if not table.startswith("sqlite_")
        }


def backup(database, assets, output):
    database, assets, output = database.resolve(), assets.resolve(), output.resolve()
    assert database.is_file() and assets.is_dir() and not output.exists()
    assert output != assets and assets not in output.parents, "Backup must be outside asset storage"
    counts = integrity(database)
    output.mkdir(parents=True)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(output / "campaigns.sqlite3")) as target:
            with target:
                source.backup(target)
                target.execute("PRAGMA journal_mode=DELETE")
    files = []
    for path in sorted(assets.rglob("*")):
        assert not path.is_symlink(), "Symlink assets cannot be backed up"
        if path.is_file():
            relative = path.relative_to(assets)
            assert path.name not in {".env", ".env.local"}, "Credential files are not assets"
            target = output / "assets" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            files.append(
                {
                    "path": relative.as_posix(),
                    "sha256": digest_file(target),
                    "bytes": target.stat().st_size,
                }
            )
    (output / "assets").mkdir(exist_ok=True)
    manifest = {
        "schema": "backup-b8.1",
        "captured_at": utc_now(),
        "database_sha256": digest_file(output / "campaigns.sqlite3"),
        "table_counts": counts,
        "assets": files,
        "credentials_included": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verify(output)
    return manifest


def verify(folder):
    folder = folder.resolve()
    assert {p.name for p in folder.iterdir()} == {"campaigns.sqlite3", "assets", "manifest.json"}
    assert not any(p.is_symlink() for p in folder.rglob("*")), "Backup links are unsafe"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "backup-b8.1"
    assert digest_file(folder / "campaigns.sqlite3") == manifest["database_sha256"]
    assert integrity(folder / "campaigns.sqlite3") == manifest["table_counts"]
    actual = {
        p.relative_to(folder / "assets").as_posix()
        for p in (folder / "assets").rglob("*")
        if p.is_file()
    }
    assert actual == {f["path"] for f in manifest["assets"]}
    for item in manifest["assets"]:
        relative = Path(item["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        path = folder / "assets" / relative
        assert not path.is_symlink() and path.resolve().is_relative_to(folder / "assets")
        assert path.stat().st_size == item["bytes"] and digest_file(path) == item["sha256"]
    return manifest


def restore(source, target):
    source, target = source.resolve(), target.resolve()
    verify(source)
    assert not target.exists(), "Restore into a new directory; never overwrite working data"
    shutil.copytree(source, target)
    return verify(target)


def main():
    parser = argparse.ArgumentParser(description="Stop the local server before backup/restore")
    actions = parser.add_subparsers(dest="operation", required=True)
    save = actions.add_parser("backup")
    save.add_argument("--database", type=Path, required=True)
    save.add_argument("--assets", type=Path, required=True)
    save.add_argument("--output", type=Path, required=True)
    load = actions.add_parser("restore")
    load.add_argument("--source", type=Path, required=True)
    load.add_argument("--output", type=Path, required=True)
    inspect = actions.add_parser("verify")
    inspect.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    result = (
        backup(args.database, args.assets, args.output)
        if args.operation == "backup"
        else (
            restore(args.source, args.output)
            if args.operation == "restore"
            else verify(args.source)
        )
    )
    print(
        json.dumps(
            {
                "operation": args.operation,
                "status": "PASS",
                "assets": len(result["assets"]),
                "database_sha256": result["database_sha256"],
                "credentials_included": False,
            }
        )
    )


if __name__ == "__main__":
    main()
