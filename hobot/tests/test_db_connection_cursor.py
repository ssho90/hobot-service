import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

from pymysql.cursors import DictCursor


_DB_PATH = Path(__file__).resolve().parents[1] / "service" / "database" / "db.py"
_DB_SPEC = spec_from_file_location("db_under_test", _DB_PATH)
assert _DB_SPEC and _DB_SPEC.loader
db = module_from_spec(_DB_SPEC)
_DB_SPEC.loader.exec_module(db)


class FakeDriverConnection:
    def __init__(self):
        self.cursorclass = None
        self.autocommit_calls = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0
        self.last_cursor_cls = None

    def cursor(self, cursor=None):
        self.last_cursor_cls = cursor or self.cursorclass
        return self.last_cursor_cls

    def autocommit(self, value):
        self.autocommit_calls.append(value)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1


class FakePooledConnection:
    def __init__(self, driver_connection):
        self.driver_connection = driver_connection

    def __getattr__(self, name):
        return getattr(self.driver_connection, name)


class FakeEngine:
    def __init__(self, pooled_connection):
        self.pooled_connection = pooled_connection

    def raw_connection(self):
        return self.pooled_connection


class TestDbConnectionCursor(unittest.TestCase):
    def test_apply_dict_cursor_updates_driver_connection(self):
        driver_connection = FakeDriverConnection()
        pooled_connection = FakePooledConnection(driver_connection)

        db._apply_dict_cursor(pooled_connection)

        self.assertIs(driver_connection.cursorclass, DictCursor)
        self.assertNotIn("cursorclass", pooled_connection.__dict__)

    def test_apply_dict_cursor_updates_direct_connection(self):
        driver_connection = FakeDriverConnection()

        db._apply_dict_cursor(driver_connection)

        self.assertIs(driver_connection.cursorclass, DictCursor)

    def test_get_db_connection_sets_dict_cursor_before_queries(self):
        driver_connection = FakeDriverConnection()
        pooled_connection = FakePooledConnection(driver_connection)
        engine = FakeEngine(pooled_connection)

        with patch.object(db, "ensure_database_initialized"), patch.object(
            db, "_get_engine", return_value=engine
        ):
            with db.get_db_connection() as conn:
                cursor_cls = conn.cursor()
                self.assertIs(cursor_cls, DictCursor)
                self.assertEqual(driver_connection.autocommit_calls, [False])

        self.assertEqual(driver_connection.commit_calls, 1)
        self.assertEqual(driver_connection.rollback_calls, 0)
        self.assertEqual(driver_connection.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
