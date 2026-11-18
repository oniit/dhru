# Task 157: Configurable Card Names & Flexible Selection for Tujuh Pusaka

## Ringkasan Eksekusi
- **Tanggal:** 19 November 2026
- **Tujuan:** Mempermudah pengelolaan dan penggantian nama-nama kartu game **Tujuh Pusaka** oleh pengelola bot tanpa merusak atau mengubah logika pertarungan kartu (`calculate_duel`), serta membuat proses pemilihan kartu oleh pemain lebih fleksibel (mendukung multi-word, nama tampilan baru, dan fallback nomor).
- **Cakupan File Diperbaiki & Ditambahkan:**
  - Game Engine: `bot/games/tujuh_pusaka.py`
  - Dokumentasi: `docs/commands.md`
  - Unit Test Suite: `tests/test_tujuh_pusaka.py`

---

## Masalah Sebelumnya
1. **Hardcoded Identifier di Banyak Tempat:**
   Nama-nama staf/karakter lama (`dika`, `nivia`, `nuansa`, `leonie`, `dyah`, `neil`) tertanam secara langsung di berbagai lapisan kode:
   - Dictionary `CARDS`
   - String `CARD_INFO`
   - Validasi error input `(Pilih: dika, nivia, nuansa, leonie, dyah, neil, pusaka)`
   - Pengecekan skill duel di dalam `calculate_duel()`
   Hal ini menyebabkan jika pengelola ingin mengganti salah satu nama kartu (misal terjadi regenerasi staf), duel battle kartu bisa rusak atau efek skill tidak aktif.
2. **Keterbatasan Input Multi-Word:**
   Perintah `/pusaka` sebelumnya memotong string dengan `parts[1]`. Untuk kartu dengan nama lebih dari satu kata (seperti `Kartu Pusaka`), pemain yang mengetik `/pusaka kartu pusaka` akan tertolak karena hanya kata pertama (`kartu`) yang terbaca.
3. **Ketidaksesuaian Sisa Kartu di Tampilan Status:**
   Fungsi `status_tujuh_pusaka` menggunakan `[c.title() for c in p_data['cards']]`, sehingga selalu mencetak ID dictionary (`Dika`, `Neil`, dll.) alih-alih nama tampilan kartu yang sebenarnya dikonfigurasi.

---

## Rincian Perubahan Teknis

### 1. Dekoupling Konfigurasi Nama Berbasis Slot Peran (`bot/games/tujuh_pusaka.py`)
- Menambahkan dictionary `NAMA_KARTU` berbasis slot peran internal di baris teratas [tujuh_pusaka.py](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/bot/games/tujuh_pusaka.py#L20-L28):
  ```python
  NAMA_KARTU = {
      "rektor": "Dika",          # Rektor (Str 90) - +15 Str vs Warek 1 & Warek 2
      "warek1": "Nivia",         # Wakil Rektor 1 (Str 75) - +20 Str vs Str lebih tinggi & batalkan bonus lawan
      "warek2": "Nuansa",        # Wakil Rektor 2 (Str 75) - +20 Str vs Sekretaris
      "sekre1": "Leonie",        # Sekretaris 1 (Str 60) - Menyalin Power lawan
      "sekre2": "Dyah",          # Sekretaris 2 (Str 60) - Membatalkan seluruh bonus lawan
      "sekre3": "Neil",          # Sekretaris 3 (Str 60) - Jika kalah, lawan -20 Str di ronde berikutnya
      "pusaka": "Kartu Pusaka",  # Pusaka (Str -) - Membalikkan hasil duel (Menang <-> Kalah)
  }
  ```
- Dictionary `CARDS` dan string panduan `get_card_info()` sekarang mengambil nilai nama secara dinamis dari `NAMA_KARTU` menggunakan key slot peran (`rektor`, `warek1`, dll.).
- Menambahkan `LEGACY_KEYS` untuk backward compatibility penuh dengan sesi atau data lama yang mungkin masih tersimpan dengan key nama (`dika`, `nivia`, dsb.).
- Logika duel `calculate_duel()` menormalisasi key legacy secara otomatis sehingga duel battle kartu tidak akan pernah terpengaruh oleh perubahan nama karakter.

### 2. Fungsi Parser & Pencocokan Fleksibel (`resolve_card_id`)
- Mengimplementasikan `resolve_card_id(card_choice: str) -> str | None` dengan hierarki pencocokan:
  1. Pencocokan langsung ID role internal (`"rektor"`, `"warek1"`, dst.).
  2. Pencocokan ID legacy (`"dika"`, `"nivia"`, dst.).
  3. Pencocokan nama tampilan yang sedang aktif secara case-insensitive.
  4. Pencocokan nama tanpa awalan `"kartu "` (contoh: pemain mengetik `"pusaka"` untuk `"Kartu Pusaka"`).
  5. Fallback angka `1 - 7` sesuai nomor urut kartu untuk kenyamanan ekstra.
- Mengubah parsing argumen pesan pada `proses_pesan_tujuh_pusaka`:
  ```python
  card_choice = " ".join(parts[1:]).strip()
  ```
  Sehingga input multi-kata seperti `/pusaka kartu pusaka` terbaca secara utuh.

### 3. Dinamisasi Pesan dan Status
- Pesan kesalahan kartu tidak valid (`pilih_kartu`) kini mencetak daftar nama aktif secara dinamis:
  `Pilihan kartu: <daftar nama aktual>`
- Status sisa kartu pemain (`status_tujuh_pusaka`) kini mengambil `CARDS.get(c, {}).get("name", c.title())` sehingga nama yang ditampilkan kepada pemain selalu akurat sesuai nama yang baru.

---

## Verifikasi & Pengujian
- Dibuat suite pengujian baru [test_tujuh_pusaka.py](file:///c:/Users/onit/OneDrive/Documents/Python/tele/dhru/tests/test_tujuh_pusaka.py) dengan 5 skenario komprehensif:
  1. `test_resolve_card_id_default_names`: Resolusi ID, case-insensitivity, strip awalan, dan fallback angka.
  2. `test_card_info_contains_names`: Memastikan seluruh nama kartu tercakup dalam panduan.
  3. `test_dynamic_rename_support`: Penggantian nama kartu di `NAMA_KARTU` secara langsung mengubah respon `resolve_card_id` dan `get_card_info()`.
  4. `test_calculate_duel_mechanics`: Logika duel (Nivia vs Dika, Pusaka reverser, draw Pusaka vs Pusaka) tetap 100% konsisten.
  5. `test_proses_pesan_and_pilih_kartu`: Alur pesan `/pusaka`, penanganan kartu tidak valid, dan input multi-kata berhasil memilih kartu pemain.
- Seluruh 5 test case **100% PASSED** dalam 1.08 detik.
- Seluruh 74 test case `test_qa_master_audit.py` dan 8 test case `test_qa_all_fixes.py` tetap **100% PASSED**.
