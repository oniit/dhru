# Fix Minor Bugs and UI Updates (Batch 016)

## Deskripsi
Menyelesaikan beberapa isu dan peningkatan kecil yang dilaporkan terkait alur kerja bot dan tampilan data, antara lain:
1. Validasi /kode tidak ada respon (ini sudah teratasi pada `015` karena *shadow import* juga menghancurkan handler `INPUT_CODE`).
2. Aksi persetujuan `/ubah` (Setujui/Tolak) tidak merespons (variabel *database connection* tidak terdefinisi pada *callback*).
3. Field "jabatan sansekerta" dan "maba group" tidak semestinya muncul di tampilan profil `public`.
4. Role/Peran belum tampil di output pesan command `/profile_dtl`.

## Tindakan yang Diambil
- **Fix Callback `/ubah`**: Menambahkan deklarasi variabel global `conn`, `db`, dan `uid` di tingkat teratas fungsi `on_callback` (`commands.py`), sehingga _action block_ persetujuan/penolakan data diri bisa tereksekusi tanpa crash `NameError`.
- **Sembunyikan Field Spesifik dari Publik**: Memperbarui rutin `display_keys_for_role` (`common.py`) agar field `maba_group` dikunci hanya untuk role `maba`, dan `position` (jabatan sansekerta) hanya muncul untuk role spesifik (seperti internal/owner/admin).
- **Tampilkan Role di `/profile_dtl`**: Menyelipkan pemanggilan `role_display` untuk menyisipkan variabel peran di bawah nomor ID pada balasan perintah `/profile_dtl`.

## Status
- **Terselesaikan (Fixed/Done)**: Keseluruhan *feedback* poin 1 s/d 4 telah diimplementasikan ke dalam basis kode.
