import asyncio
import random
import json
import aiosqlite
import os
import sys

# Append parent dir to path so we can import bot modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from bot.database import Database

async def main():
    if os.path.exists("test_bot.db"):
        os.remove("test_bot.db")
    
    db = Database()
    conn = await aiosqlite.connect("test_bot.db")
    conn.row_factory = aiosqlite.Row
    # Because init_db doesn't exist, we just run the table creation manually for the tables we need.
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        language_code TEXT,
        is_premium INTEGER,
        is_bot INTEGER,
        role TEXT NOT NULL DEFAULT 'public',
        profile_json TEXT,
        agra_total INTEGER NOT NULL DEFAULT 0,
        onboarding_step INTEGER,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""")
    
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS user_chat_stats (
        user_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,
        message_count INTEGER NOT NULL DEFAULT 0,
        last_active_at REAL NOT NULL,
        PRIMARY KEY (user_id, chat_id)
    )""")
    await conn.commit()
    
    NUM_MABAS = 125 # 125 total to test remainder behavior
    
    print(f"1. Menciptakan {NUM_MABAS} Maba...")
    import time
    now = time.time()
    for i in range(1, NUM_MABAS + 1):
        uid = 1000 + i
        await conn.execute("INSERT INTO users (telegram_id, role, profile_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)", (uid, "public", "{}", now, now))
        
        rand = random.random()
        if rand < 0.3:
            msg_count = random.randint(50, 200)
        elif rand < 0.7:
            msg_count = random.randint(10, 49)
        else:
            msg_count = random.randint(0, 9)
            
        if msg_count > 0:
            await conn.execute("INSERT INTO user_chat_stats (user_id, chat_id, message_count, last_active_at) VALUES (?, ?, ?, ?)", (uid, 9999, msg_count, now))
                
    await conn.commit()
    
    tiers = await db.get_all_users_chat_tiers(conn)
    tier_counts = {"A": 0, "B": 0, "C": 0}
    for uid in range(1001, 1001 + NUM_MABAS):
        t = tiers.get(uid, "C")
        tier_counts[t] += 1
    print(f"2. Klasifikasi Tier Selesai: {tier_counts}")
    
    print("3. Memulai proses rebutan kode maba (Sequential Plotting)...")
    user_ids = [1000 + i for i in range(1, NUM_MABAS + 1)]
    random.shuffle(user_ids)
    
    for idx, uid in enumerate(user_ids, 1):
        await conn.execute("UPDATE users SET role = 'maba' WHERE telegram_id = ?", (uid,))
        await conn.commit()
        
        user_tier = await db.get_user_chat_tier(conn, uid)
        
        cur_mabas = await conn.execute("SELECT telegram_id, profile_json FROM users WHERE role = 'maba'")
        all_mabas = await cur_mabas.fetchall()
        
        t_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        total_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        
        all_tiers = await db.get_all_users_chat_tiers(conn)
        
        for r in all_mabas:
            if str(r["telegram_id"]) == str(uid):
                continue
            prof = json.loads(r["profile_json"]) if r["profile_json"] else {}
            mg = int(prof.get("maba_group", 0))
            if 1 <= mg <= 4:
                total_counts[mg] += 1
                t = all_tiers.get(r["telegram_id"], "C")
                if t == user_tier:
                    t_counts[mg] += 1
                    
        min_tier_count = min(t_counts.values())
        candidate_groups = [g for g, c in t_counts.items() if c == min_tier_count]
        
        if len(candidate_groups) == 1:
            maba_group = candidate_groups[0]
        else:
            min_total = min(total_counts[g] for g in candidate_groups)
            best_groups = [g for g in candidate_groups if total_counts[g] == min_total]
            maba_group = best_groups[0]
            
        await db.set_profile_partial(conn, uid, {"maba_group": maba_group})
        if idx % 25 == 0:
            print(f"   [{idx}/{NUM_MABAS}] maba telah diplot...")
            
    print("\n--- HASIL AKHIR DISTRIBUSI KELOMPOK ---")
    cur_mabas = await conn.execute("SELECT telegram_id, profile_json FROM users WHERE role = 'maba'")
    all_mabas = await cur_mabas.fetchall()
    
    group_stats = {1: {"total": 0, "A": 0, "B": 0, "C": 0},
                   2: {"total": 0, "A": 0, "B": 0, "C": 0},
                   3: {"total": 0, "A": 0, "B": 0, "C": 0},
                   4: {"total": 0, "A": 0, "B": 0, "C": 0}}
                   
    for r in all_mabas:
        uid = r["telegram_id"]
        prof = json.loads(r["profile_json"]) if r["profile_json"] else {}
        mg = int(prof.get("maba_group", 0))
        t = all_tiers.get(uid, "C")
        if 1 <= mg <= 4:
            group_stats[mg]["total"] += 1
            group_stats[mg][t] += 1
            
    for g, stats in group_stats.items():
        print(f"Kelompok {g} -> Total Kepala: {stats['total']} | Komposisi Tier: A={stats['A']}, B={stats['B']}, C={stats['C']}")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
