"""Offline tests for the local SQLite backup/restore helper."""

import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.sqlite_backup import (
    _backup_database,
    create_backup,
    restore_backup,
    verify_database,
)


def create_fixture(path, *, include_herd_data=True):
    with closing(sqlite3.connect(path)) as database:
        with database:
            if include_herd_data:
                database.executescript(
                    "CREATE TABLE herd_herd (id INTEGER PRIMARY KEY, code TEXT NOT NULL);"
                    "CREATE TABLE care_careschedule (id INTEGER PRIMARY KEY, herd_id INTEGER, activity TEXT);"
                    "CREATE TABLE care_carelog (id INTEGER PRIMARY KEY, herd_id INTEGER, activity TEXT);"
                    "INSERT INTO herd_herd (code) VALUES ('FIXTURE-HERD');"
                    "INSERT INTO care_careschedule (herd_id, activity) VALUES (1, 'fixture schedule');"
                    "INSERT INTO care_carelog (herd_id, activity) VALUES (1, 'fixture log');"
                )
            else:
                database.execute("CREATE TABLE old_database (id INTEGER PRIMARY KEY, value TEXT)")
                database.execute("INSERT INTO old_database (value) VALUES ('preserved safety copy')")


def schema_and_counts(path):
    with closing(sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)) as database:
        schema = database.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        tables = database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        counts = {}
        for (table_name,) in tables:
            quoted = '"' + table_name.replace('"', '""') + '"'
            counts[table_name] = database.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
        return schema, counts


class SQLiteBackupRestoreTests(unittest.TestCase):
    def test_snapshot_restore_preserves_schema_and_business_row_counts(self):
        with tempfile.TemporaryDirectory(prefix="sqlite-backup-test-") as temporary:
            root = Path(temporary)
            database_path = root / "source.sqlite3"
            backup_directory = root / "backups"
            restored_path = root / "restored.sqlite3"
            create_fixture(database_path)
            create_fixture(restored_path, include_herd_data=False)

            snapshot_path = create_backup(database_path, backup_directory)
            self.assertIn("backup-", snapshot_path.name)
            safety = None
            restored, safety = restore_backup(restored_path, snapshot_path, backup_directory)

            self.assertEqual(restored, restored_path.resolve())
            self.assertTrue(safety.is_file())
            self.assertEqual(schema_and_counts(snapshot_path), schema_and_counts(restored_path))
            _, counts = schema_and_counts(restored_path)
            self.assertEqual(counts["care_careschedule"], 1)
            self.assertEqual(counts["care_carelog"], 1)
            with closing(sqlite3.connect(f"file:{safety.as_posix()}?mode=ro", uri=True)) as safety_copy:
                self.assertEqual(
                    safety_copy.execute("SELECT COUNT(*) FROM old_database").fetchone()[0], 1,
                )

    def test_backup_refuses_to_overwrite_existing_destination(self):
        with tempfile.TemporaryDirectory(prefix="sqlite-backup-test-") as temporary:
            root = Path(temporary)
            source = root / "source.sqlite3"
            existing = root / "existing-backup.sqlite3"
            create_fixture(source)
            existing.write_bytes(b"keep this existing file")

            with self.assertRaises(FileExistsError):
                _backup_database(source, existing)
            self.assertEqual(existing.read_bytes(), b"keep this existing file")

    def test_invalid_restore_source_does_not_replace_target(self):
        with tempfile.TemporaryDirectory(prefix="sqlite-backup-test-") as temporary:
            root = Path(temporary)
            target = root / "target.sqlite3"
            invalid_backup = root / "invalid.sqlite3"
            create_fixture(target, include_herd_data=False)
            original = schema_and_counts(target)
            invalid_backup.write_bytes(b"not a SQLite database")

            with self.assertRaises(sqlite3.DatabaseError):
                restore_backup(target, invalid_backup, root / "backups")
            self.assertEqual(schema_and_counts(target), original)

    def test_restore_refuses_target_sidecars_without_changing_them(self):
        with tempfile.TemporaryDirectory(prefix="sqlite-backup-test-") as temporary:
            root = Path(temporary)
            source = root / "source.sqlite3"
            target = root / "target.sqlite3"
            backups = root / "backups"
            create_fixture(source)
            create_fixture(target, include_herd_data=False)
            snapshot = create_backup(source, backups)
            original_bytes = target.read_bytes()
            wal = Path(f"{target}-wal")
            shm = Path(f"{target}-shm")
            wal.write_bytes(b"preserve WAL sidecar")
            shm.write_bytes(b"preserve SHM sidecar")

            with self.assertRaisesRegex(ValueError, "Close every application.*checkpoint"):
                restore_backup(target, snapshot, backups)

            self.assertEqual(target.read_bytes(), original_bytes)
            self.assertEqual(wal.read_bytes(), b"preserve WAL sidecar")
            self.assertEqual(shm.read_bytes(), b"preserve SHM sidecar")
            self.assertFalse(backups.exists() and list(backups.glob("*before-restore*")))

    def test_replace_failure_preserves_target_and_safety_copy_and_cleans_temp(self):
        with tempfile.TemporaryDirectory(prefix="sqlite-backup-test-") as temporary:
            root = Path(temporary)
            source = root / "source.sqlite3"
            target = root / "target.sqlite3"
            backups = root / "backups"
            create_fixture(source)
            create_fixture(target, include_herd_data=False)
            original = schema_and_counts(target)
            snapshot = create_backup(source, backups)

            with patch("tools.sqlite_backup.os.replace", side_effect=OSError("injected replace failure")):
                with self.assertRaisesRegex(OSError, "safety backup is retained at") as raised:
                    restore_backup(target, snapshot, backups)

            self.assertIn("injected replace failure", str(raised.exception))
            self.assertEqual(schema_and_counts(target), original)
            safety_path = next(backups.glob("*before-restore-*.sqlite3"))
            self.assertTrue(safety_path.is_file())
            self.assertIn(str(safety_path), str(raised.exception))
            self.assertEqual(verify_database(safety_path), safety_path.resolve())
            self.assertEqual(schema_and_counts(safety_path), original)
            self.assertEqual(list(root.glob(".target.sqlite3.*.restore")), [])
            self.assertEqual(list(root.glob(".target.sqlite3.*.restore-wal")), [])
            self.assertEqual(list(root.glob(".target.sqlite3.*.restore-shm")), [])


if __name__ == "__main__":
    unittest.main()
