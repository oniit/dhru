# Task 018: Fix AiosqliteRowMock implementation for Turso db
    
## Latar Belakang
Ditemukan dua *bug* yang dilaporkan oleh user saat menggunakan bot (yang menggunakan integrasi database LibSQL/Turso):
1. **Memasukkan kode akademik tidak merespon:** Saat user memasukkan kode akademik pada proses registrasi, bot tidak memberikan respon apapun dan mengabaikan masukan kode tersebut.
2. **Admin/Owner tidak bisa menyetujui (acc) atau menolak (decline) usulan perubahan:** Saat menekan tombol acc/decline, aksi tersebut gagal dieksekusi.

## Akar Masalah
Masalah ini ternyata disebabkan oleh implementasi struktur `AiosqliteRowMock` di `bot/database.py` yang digunakan sebagai pembungkus (*wrapper*) tipe row pada saat menggunakan Turso (`libsql_client`). 
Struktur *mock* ini mendefinisikan `self.keys = columns` secara langsung sebagai atribut (berupa *list*). Sementara itu, standar `sqlite3.Row` (dan `aiosqlite.Row`) mendefinisikan `.keys()` sebagai sebuah **metode** yang dapat dipanggil (`callable`), serta mengimplementasikan iterasi.
- **Bug 1:** Pada pengecekan di `messages.py` baris 147, terdapat kode `"target_role" in code_row.keys()`. Pemanggilan fungsi `keys()` pada *list* memicu `TypeError: 'list' object is not callable`. Karena tidak ada penangkapan *exception*, aksi tersebut terhenti tanpa memberikan merespon ke pengguna.
- **Bug 2:** Pada `commands.py` untuk menyebarkan pesan saat persetujuan pengajuan perubahan profil, terdapat sintaks `dict(req)`. Pembentukan *dictionary* dari objek `Row` memicu pemanggilan `.keys()` secara internal. Akibatnya, pelemparan `TypeError` pun terjadi yang menggagalkan fungsionalitas `acc/decline`.

## Perubahan yang Dilakukan
- Memodifikasi *class* `AiosqliteRowMock` pada `bot/database.py` agar berperilaku mirip seperti `sqlite3.Row` seutuhnya:
  - Mengubah atribut `self.keys` menjadi `self._keys` yang *private*.
  - Menambahkan *method* `keys()` agar dapat dipanggil menggunakan tanda kurung (seperti `row.keys()`).
  - Mengubah logika pemanggilan `self.keys` menjadi `self._keys` di bagian `__getitem__`.
  - Menambahkan *method* `__iter__` untuk mengembalikan iterator pada nama-nama kolom, yang diwajibkan oleh fungsi `dict()`.

Perubahan ini bersifat internal dan tidak mengubah arsitektur, perintah bot (*commands*), ataupun skema basis data (*database*).
