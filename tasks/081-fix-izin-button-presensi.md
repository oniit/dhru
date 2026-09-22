# 081 — Fix Tombol Izin Presensi Manual

## Masalah
Tombol "⏸️ Izin" pada sesi presensi manual (yang dibuka via `/presensi buka`) tampak tidak berfungsi. Ketika user klik tombol Izin, tidak ada perubahan visual pada pesan pengumuman presensi.

## Penyebab (Root Cause)
Bug indentasi di fungsi `_format_presensi_block` pada `bot/handlers/attendance.py`.

Bagian Izin (`Izin (N)`) berada **di dalam `else` block** dari `if not hadir_records:`. Artinya, bagian daftar Izin **hanya ditampilkan jika sudah ada setidaknya satu orang Hadir**.

Skenario gagal:
1. Sesi dibuka → belum ada peserta → tampil `Hadir (0) - Belum ada.`
2. User klik **Izin** → record tersimpan ke database ✅
3. `refresh_presensi_announcement` dipanggil → `edit_message_text` berhasil ✅
4. Tapi `_format_presensi_block` **tidak menampilkan bagian Izin** karena `hadir_records` masih kosong ❌
5. Pesan tidak berubah → user melihat "error"

## Perbaikan
Memindahkan blok Izin (`if sess["class_id"] not in ("staff_auto", "maba_auto"):`) **keluar** dari `else` block, sehingga blok Izin selalu ditampilkan secara independen, terlepas dari ada/tidaknya record Hadir.

### Sebelum (salah)
```python
if not hadir_records:
    lines.append("Belum ada.")
else:
    for r in hadir_records:
        ...
    # ← BUG: blok Izin di dalam else
    if sess["class_id"] not in ("staff_auto", "maba_auto"):
        lines.append(f"Izin ({len(izin_records)})")
        ...
```

### Sesudah (benar)
```python
if not hadir_records:
    lines.append("Belum ada.")
else:
    for r in hadir_records:
        ...

# ← Di luar else, selalu tampil
if sess["class_id"] not in ("staff_auto", "maba_auto"):
    lines.append(f"Izin ({len(izin_records)})")
    ...
```

## File Diubah
- `bot/handlers/attendance.py` — `_format_presensi_block()` (line ~134-165)
