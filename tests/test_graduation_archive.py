import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
from bot.database import Database
import bot.graduation_excel as ge


class SqliteMockConn:
    def __init__(self, raw_conn):
        self.raw_conn = raw_conn

    async def execute(self, sql, params=()):
        cur = self.raw_conn.execute(sql, params)
        class CurMock:
            def __init__(self, c):
                self.c = c
            async def fetchall(self):
                return self.c.fetchall()
            async def fetchone(self):
                return self.c.fetchone()
        return CurMock(cur)

    async def commit(self):
        self.raw_conn.commit()

    async def close(self):
        self.raw_conn.close()


def run_all_tests():
    print("Test 1: Testing get_student_by_nim from JSON archive...", flush=True)
    s1 = ge.get_student_by_nim("02004010093")
    assert s1 is not None, "Failed to find student by 11-digit NIM"
    print("Found student:", s1.nama, f"({s1.jurusan})", flush=True)

    s1_short = ge.get_student_by_nim("2004010093")
    assert s1_short is not None, "Failed to find student by 10-digit NIM"
    assert s1_short.nama == s1.nama
    print("Short NIM lookup verified!", flush=True)

    print("Test 2: Testing get_student_by_name...", flush=True)
    s2 = ge.get_student_by_name("Aluna Valencia")
    assert s2 is not None
    assert s2.nim == s1.nim

    s2_sub = ge.get_student_by_name("Aluna")
    assert s2_sub is not None
    assert s2_sub.nim == s1.nim
    print("Name lookup verified!", flush=True)

    print("Test 3: Testing serialization and deserialization...", flush=True)
    d = s1.to_dict()
    restored = ge.StudentGraduationData.from_dict(d)
    assert restored.nama == s1.nama
    assert restored.nim == s1.nim
    assert restored.ipk == s1.ipk
    assert restored.predikat == s1.predikat
    assert len(restored.courses) == len(s1.courses)
    assert len(restored.clubs) == len(s1.clubs)
    print("Serialization verified!", flush=True)

    print("Test 4: Testing DB mirroring with mock connection...", flush=True)
    raw_sqlite = sqlite3.connect(":memory:")
    raw_sqlite.row_factory = sqlite3.Row
    raw_sqlite.execute(
        "CREATE TABLE IF NOT EXISTS graduation_records ("
        "    nim TEXT PRIMARY KEY,"
        "    nama TEXT NOT NULL,"
        "    generasi TEXT NOT NULL,"
        "    data_json TEXT NOT NULL,"
        "    created_at REAL NOT NULL,"
        "    updated_at REAL NOT NULL"
        ");"
    )
    raw_sqlite.commit()
    conn = SqliteMockConn(raw_sqlite)
    db = Database()

    def run_sync(coro):
        try:
            coro.send(None)
        except StopIteration as e:
            return e.value
        raise RuntimeError("Coroutine did not finish synchronously")

    count = run_sync(ge.mirror_archive_to_turso(conn, db, [s1]))
    assert count == 1, f"Expected 1 mirrored record, got {count}"
    print(f"Mirrored {count} record to database successfully!", flush=True)

    from_db = run_sync(db.get_all_graduation_records_from_db(conn))
    assert len(from_db) == 1, f"Expected 1 from DB, got {len(from_db)}"
    assert from_db[0]["nim"] == s1.nim
    assert from_db[0]["nama"] == s1.nama
    print(f"Successfully fetched {len(from_db)} records from database!", flush=True)
    raw_sqlite.close()

    print("Test 5: Testing multi-generation filtering...", flush=True)
    grads_gen1 = ge.get_all_graduates(generasi="1")
    grads_all = ge.get_all_graduates()
    assert len(grads_gen1) == len(grads_all)
    assert len(grads_all) == 21
    print(f"Gen 1 graduates count: {len(grads_gen1)}", flush=True)

    print("\n>>> ALL GRADUATION ARCHIVE TESTS PASSED SUCCESSFULLY! <<<", flush=True)


if __name__ == "__main__":
    print("ENTERING MAIN", flush=True)
    run_all_tests()
