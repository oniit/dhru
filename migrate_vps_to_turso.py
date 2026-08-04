import asyncio
import os
import sqlite3
import libsql_client
from dotenv import load_dotenv

async def main():
    load_dotenv(".env")
    url = os.environ.get("TURSO_DB_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if not url or not token:
        print("URL atau Token Turso tidak ditemukan di .env")
        return

    local_db_path = "data/bot.db"
    if not os.path.exists(local_db_path):
        print(f"Database lokal tidak ditemukan di {local_db_path}")
        return

    print(f"Menghubungkan ke database lokal: {local_db_path}")
    conn = sqlite3.connect(local_db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row["name"] for row in cur.fetchall()]

    print(f"Menghubungkan ke Turso: {url}")
    client = libsql_client.create_client(url=url, auth_token=token)

    try:
        # Import schema and create tables if they don't exist
        from bot.database import SCHEMA
        print("Mengeksekusi skema database pada Turso...")
        
        try:
            await client.execute("PRAGMA foreign_keys = OFF;")
            print("Foreign keys dinonaktifkan sementara untuk migrasi.")
        except Exception:
            pass
            
        # Execute schema might require splitting by ';'
        statements = [s.strip() for s in SCHEMA.split(';') if s.strip()]
        for stmt in statements:
            try:
                await client.execute(stmt)
            except Exception:
                pass
                
        print("Menambahkan kolom-kolom baru (ALTER TABLE) jika belum ada...")
        alter_stmts = [
            "ALTER TABLE attendance_sessions ADD COLUMN announce_message_id INTEGER",
            "ALTER TABLE profile_change_requests ADD COLUMN moderator_prompt_text TEXT",
            "ALTER TABLE attendance_records ADD COLUMN status TEXT NOT NULL DEFAULT 'hadir'",
            "ALTER TABLE access_codes ADD COLUMN target_role TEXT NOT NULL DEFAULT 'student'"
        ]
        for stmt in alter_stmts:
            try:
                await client.execute(stmt)
            except Exception:
                pass

        for table in tables:
            print(f"Migrasi tabel {table}...")
            cur.execute(f"SELECT * FROM {table}")
            rows = cur.fetchall()
            if not rows:
                print(f"  Tabel {table} kosong. Lewati.")
                continue

            columns = rows[0].keys()
            placeholders = ", ".join(["?"] * len(columns))
            cols_str = ", ".join(columns)
            
            insert_sql = f"INSERT OR REPLACE INTO {table} ({cols_str}) VALUES ({placeholders})"
            
            # Batch execution to prevent rate limiting
            chunk_size = 50
            count = 0
            for i in range(0, len(rows), chunk_size):
                chunk = rows[i:i + chunk_size]
                stmts = []
                for row in chunk:
                    values = [row[col] for col in columns]
                    stmts.append(libsql_client.Statement(insert_sql, values))
                try:
                    if hasattr(client, 'batch'):
                        await client.batch(stmts)
                        count += len(chunk)
                    else:
                        raise AttributeError("No batch method")
                except Exception as e:
                    # Fallback ke sequential dengan delay
                    for row in chunk:
                        values = [row[col] for col in columns]
                        try:
                            await client.execute(insert_sql, values)
                            count += 1
                        except Exception as inner_e:
                            print(f"    Gagal baris spesifik: {repr(inner_e)} | Data: {values}")
                        await asyncio.sleep(0.05)
            
            print(f"  Berhasil memigrasi {count}/{len(rows)} baris ke tabel {table}.")
            
        print("✅ Migrasi selesai!")
    except Exception as e:
        print(f"❌ Terjadi kesalahan saat migrasi: {e}")
    finally:
        await client.close()
        conn.close()

if __name__ == "__main__":
    asyncio.run(main())
