# Perbaikan Celah Keamanan (QA Fixes) - Selesai

## Konteks & Laporan Bug
Melalui audit _Senior QA_ mendalam terhadap codebase, ditemukan celah keamanan yang sangat krusial pada alur manipulasi profil.

### Privilege Escalation pada `/admin_data`
- **Gejala**: Perintah `/admin_data` menggunakan filter otorisasi `can_report()`. `can_report` memberi lampu hijau pada Dekan (atau siapapun dengan bendera `d_dekan`) untuk mengaksesnya. Namun perintah `/admin_data` memungkinkan _Bypass Edit_ profil (tanpa _approval queue_). Artinya, Dekan bisa mengedit nama, NIM, atau entitas apapun milik siapa saja, termasuk milik **Owner** dan **Admin Utama**.
- **Perbaikan**: Mengganti `can_report` menjadi `can_approve_profile` di `commands.py` (`cmd_admin_data`) dan di `messages.py` (`ADMIN_TEXT_LC`). Kini fungsi `/admin_data` terkunci khusus bagi Owner, Admin, dan HR.

### Kebocoran Menu `/owner_reset`
- **Gejala**: Tombol dan menu muncul saat `/owner_reset` diketik oleh Admin (karena bocor oleh `can_approve_profile`), walau eksekusi akhirnya ditolak.
- **Perbaikan**: Diubah dengan proteksi absolut menggunakan `is_owner(update.effective_user.id)` pada level fungsi kemunculan pesannya di `commands.py`.

_Status: Terselesaikan dan digabungkan ke kode produksi._
