# Task 110: Pembaruan Struktur Organisasi Jabatan & Penambahan Divisi Pendaftaran Chāryārthī

## Ringkasan Perubahan
Berdasarkan bagan arsitektur organisasi terbaru kampus Dhruva:
1. **Nayaka (Pimpinan Eksekutif Tertinggi — Tidak Dibuka untuk Calon Staf / Chāryārthī)**:
   - Adhipati: Rektor (`d_rektor`)
   - Pratinidhi: Wakil Rektor (I, II, III — `d_warek1`, `d_warek2`, `d_warek3`)
   - Sachiva: Sekretaris (`d_sekre`)

2. **Divisi yang Dibuka untuk Calon Staf (Chāryārthī) — Seluruh Job Non-Nayaka (Total 11 Divisi)**:
   - **Acharya (Biro Akademik - Pratinidhi I)**:
     - Dekan (`d_dekan`) — Pradhānāchārya
     - Guru Besar (`d_guru_besar`) — Prāchārya
     - Dosen (`d_dosen`) — Āchārya
     - Pelatih UKM (`d_coach`) — Āchāryaka
     - Pembina BEM (`d_pembina`) — Āchāryata
   - **Pacharya (Biro Umum - Pratinidhi II)**:
     - Editorial & Konten (`d_editor`) — Śilpāchārya
     - Pengembangan SDM (`d_hrd`) — Upāchārya
     - Sarana & Prasarana (`d_sarpras`) — Parichārya
   - **Yacharya (Biro Eksternal - Pratinidhi III)**:
     - MPPS (`d_mpps`) — Kāryāchārya
     - PFP (`d_pfp`) — Taryāchārya
     - PR (`d_pr`) — Chitrayāchārya

## Solusi & Detail Teknis
1. **Pembaruan `config/choices.yaml`**:
   - Memperbarui `positions` dengan menambahkan `warek3`, `karyacharya`, `taryacharya`, dan `citrayacharya`.
   - Menambahkan detail jabatan baru pada `position_details`: `d_warek3`, `d_mpps`, `d_pfp`, `d_pr`, serta mempertahankan fallback kompatibilitas untuk `d_eksternal`.
2. **Pembaruan `bot/settings.py`**:
   - `get_charyarthi_divisions()` kini hanya mengecualikan jajaran Nayaka (`d_rektor`, `d_sekre`, `d_warek1`, `d_warek2`, `d_warek3`) serta penugasan khusus (`p_panitia_ospek`, `d_eksternal`, `d_lain`).
   - `d_dekan`, `d_guru_besar`, dan `d_pembina` kini resmi dibuka dan muncul sebagai pilihan divisi yang dapat didaftar.
   - `resolve_division_id()` diperkaya dengan alias untuk seluruh 11 divisi baru (`dekan`, `gurubesar`, `dosen`, `pelatih`, `pembina`, `editor`, `sdm`/`hrd`, `sarpras`, `mpps`, `pfp`, `pr`/`humas`).
3. **Dokumentasi & Testing**:
   - Memperbarui `docs/commands.md` pada daftar divisi `/soal`.
   - Menyesuaikan penegasan tes pada `tests/test_charyarthi.py` agar menguji ke-11 divisi terbuka.
