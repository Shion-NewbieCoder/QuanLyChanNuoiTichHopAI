"""Create consistent SQLite snapshots and safely restore a local demo database."""

import argparse
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import sys
import uuid


def _read_only_connection(path):
    path = Path(path).resolve(strict=True)
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=10)


def _check_integrity(connection):
    result = connection.execute("PRAGMA integrity_check").fetchone()
    if result != ("ok",):
        raise sqlite3.DatabaseError(f"SQLite integrity_check failed: {result!r}")


def _reserve_new_file(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)


def _backup_database(source_path, destination_path):
    source_path = Path(source_path).resolve(strict=True)
    destination_path = Path(destination_path).resolve()
    if source_path == destination_path:
        raise ValueError("Source and destination must be different files.")

    _reserve_new_file(destination_path)
    source = destination = None
    try:
        source = _read_only_connection(source_path)
        destination = sqlite3.connect(destination_path, timeout=10)
        source.backup(destination)
        destination.commit()
        _check_integrity(destination)
    except Exception:
        if destination is not None:
            destination.close()
            destination = None
        if source is not None:
            source.close()
            source = None
        destination_path.unlink(missing_ok=True)
        for sidecar in (Path(f"{destination_path}-wal"), Path(f"{destination_path}-shm")):
            sidecar.unlink(missing_ok=True)
        raise
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()
    return destination_path


def _new_timestamped_path(directory, database_stem, label):
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    return Path(directory) / f"{database_stem}-{label}-{timestamp}.sqlite3"


def _refuse_target_sidecars(database_path):
    sidecars = [
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
    ]
    present = [path for path in sidecars if path.exists()]
    if present:
        names = ", ".join(str(path) for path in present)
        raise ValueError(
            f"Restore refused because SQLite sidecar(s) remain: {names}. "
            "Close every application using this database and let SQLite "
            "close/checkpoint cleanly; do not delete the sidecars manually."
        )


def create_backup(database_path, backup_directory):
    database_path = Path(database_path).resolve(strict=True)
    backup_path = _new_timestamped_path(backup_directory, database_path.stem, "backup")
    return _backup_database(database_path, backup_path)


def restore_backup(database_path, backup_path, backup_directory=None):
    database_path = Path(database_path).resolve()
    backup_path = Path(backup_path).resolve(strict=True)
    if database_path == backup_path:
        raise ValueError("The selected backup and restore target must be different files.")
    if not database_path.parent.is_dir():
        raise FileNotFoundError(f"Database directory does not exist: {database_path.parent}")

    with closing(_read_only_connection(backup_path)) as backup:
        _check_integrity(backup)

    # These checks do not prove that no process has the database open. The
    # caller must stop every process that can use it before restoring.
    _refuse_target_sidecars(database_path)
    safety_backup = None
    if database_path.exists():
        safety_directory = Path(backup_directory) if backup_directory else database_path.parent
        safety_path = _new_timestamped_path(safety_directory, database_path.stem, "before-restore")
        safety_backup = _backup_database(database_path, safety_path)

    temporary_path = database_path.with_name(f".{database_path.name}.{uuid.uuid4().hex}.restore")
    try:
        _backup_database(backup_path, temporary_path)
        _refuse_target_sidecars(database_path)
        os.replace(temporary_path, database_path)
    except Exception as error:
        if safety_backup is not None:
            raise OSError(
                f"Restore failed; the safety backup is retained at {safety_backup}. "
                f"The restore target was not replaced: {error}"
            ) from error
        raise
    finally:
        temporary_path.unlink(missing_ok=True)
        Path(f"{temporary_path}-wal").unlink(missing_ok=True)
        Path(f"{temporary_path}-shm").unlink(missing_ok=True)

    return database_path, safety_backup


def verify_database(database_path):
    with closing(_read_only_connection(database_path)) as database:
        _check_integrity(database)
    return Path(database_path).resolve(strict=True)


def _parser():
    parser = argparse.ArgumentParser(description="Back up or restore a local SQLite demo database.")
    commands = parser.add_subparsers(dest="command", required=True)

    backup = commands.add_parser("backup", help="Create a timestamped consistent snapshot.")
    backup.add_argument("--database", required=True, type=Path, help="SQLite file resolved from Django settings.")
    backup.add_argument("--backup-dir", required=True, type=Path, help="Directory for a new snapshot.")

    restore = commands.add_parser("restore", help="Restore a snapshot after stopping all database writers.")
    restore.add_argument("--database", required=True, type=Path, help="SQLite target resolved from Django settings.")
    restore.add_argument("--backup", required=True, type=Path, help="Existing snapshot to restore.")
    restore.add_argument("--backup-dir", type=Path, help="Directory for the automatic pre-restore safety snapshot.")

    verify = commands.add_parser("verify", help="Run SQLite integrity_check without changing the database.")
    verify.add_argument("--database", required=True, type=Path, help="SQLite file to check read-only.")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "backup":
            backup = create_backup(args.database, args.backup_dir)
            print(f"BACKUP_CREATED: {backup}")
            print("INTEGRITY_CHECK: ok")
            return 0

        if args.command == "verify":
            database = verify_database(args.database)
            print(f"INTEGRITY_CHECK: ok ({database})")
            return 0

        restored, safety_backup = restore_backup(args.database, args.backup, args.backup_dir)
        print(f"RESTORE_COMPLETED: {restored}")
        print("INTEGRITY_CHECK: ok")
        if safety_backup:
            print(f"SAFETY_BACKUP_CREATED: {safety_backup}")
        return 0
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"SQLITE_BACKUP_ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
