# Maba Registration Flow (Camaba)

## Apa yang Dikerjakan
Menambahkan alur pendaftaran khusus untuk Mahasiswa Baru (Maba) atau Calon Mahasiswa Baru (Camaba) yang berada di luar alur gencode biasa.

## Mengapa Dikerjakan
- Sebelumnya, Maba langsung menggunakan gencode untuk pendaftaran. Namun, alur ini diubah agar Maba harus mengisi nama, alasan bergabung, dan **wajib mem-follow channel tertentu** sebelum bisa mendapatkan akses ke grup OSPEK tempat gencode dibagikan.

## Bagaimana Alur Kodenya Bekerja Secara Teknis
1. **Settings & Konfigurasi** (`bot/settings.py` & `config/profile_fields.yaml`):
   - `MABA_CH_IDS`: Variabel dari environment (`.env`) yang berupa *comma-separated* list berisi ID channel yang harus di-follow oleh Maba.
   - `MABA_GROUP_LINK`: Tautan invite grup OSPEK yang dibagikan otomatis setelah Maba berhasil diverifikasi.
   - Penambahan `join_reason` pada profil khusus `roles: [maba]`.
2. **Commands (`cmd_start`)**:
   - Jika pengguna memiliki `ROLE_PUBLIC`, tombol **Daftar Maba** akan muncul di bawah menu profil, yang akan memicu `maba:start`.
3. **State Machine (`messages.py`)**:
   - `MABA_NAME`: Meminta dan menyimpan nama.
   - `MABA_REASON`: Meminta alasan bergabung, kemudian meminta verifikasi channel dengan tombol "Verifikasi Kembali".
4. **Verifikasi (`commands.py - on_callback`)**:
   - Jika tombol verifikasi diklik (`maba:verify`), bot akan memanggil `get_chat_member` untuk tiap channel di `MABA_CH_IDS`. Jika semua valid, role diubah menjadi `maba` dan link grup diberikan.
5. **Profile Detail (`commands.py - cmd_profile_dtl`)**:
   - Menambahkan field "Alasan Bergabung" pada tampilan `/profile_dtl` (opsional jika user memilikinya di databasenya).

## Fitur Invite Unik & Request to Join
- **Grup Kelompok (MABA_GROUP_GIDS)**: Menggunakan \create_chat_invite_link\ untuk meng-generate tautan undangan unik 1-kali-pakai berdasarkan ID grup yang di-*set* di \.env\.
- **Grup OSPEK General (Request to Join)**: Menambahkan \ChatJoinRequestHandler\ yang akan memeriksa apakah partisipan yang *request to join* memiliki peran \maba\. Jika iya, bot otomatis memanggil \pprove_chat_join_request\.
