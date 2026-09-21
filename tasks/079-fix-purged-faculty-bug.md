# Fix Purged Faculty Bug in Chained Selection

## Deskripsi
Dalam proses pengujian (QA) alur pendaftaran Fakultas dan Jurusan secara berantai (chained selection), ditemukan sebuah bug di mana data fakultas (`faculty`) tidak tersimpan di profil akhir. Walaupun fakultas dipilih dan disimpan sementara, saat jurusan dipilih (di menu `/lengkapi`), fakultas tersebut otomatis terhapus sesaat setelah profil disimpan.

## Penyebab
Fungsi `_revalidate_filtered_choice_fields` bertugas membersihkan field yang tidak valid jika terjadi perubahan profil (contoh: mengganti jurusan yang tidak sesuai dengan fakultasnya). Fungsi ini mengecek apakah field tersebut berlaku untuk *role* dari pengguna yang sedang diperiksa melalui `field_applies_to_role`.
Karena pada pembaruan sebelumnya (tasks 078) kita telah menyembunyikan field `faculty` bagi `student` dengan setelan `roles: ['_hidden']` di file `profile_fields.yaml`, fungsi `field_applies_to_role` membaca bahwa `faculty` tidak berlaku bagi `student`.
Akibatnya, fungsi pembersih ini mengasumsikan field `faculty` adalah *field nyasar* yang tidak dibutuhkan oleh `student` dan menghapusnya dari data `profile_json` di database.

## Solusi
Menambahkan pengecualian eksplisit untuk field `faculty` di fungsi `_revalidate_filtered_choice_fields` di dalam `bot/handlers/commands.py`.
Pengecualian tersebut memastikan bahwa walaupun field `faculty` berstatus tersembunyi (hidden), field tersebut tidak akan di-purge dari profil untuk role mahasiswa/BEM/maba, karena keberadaannya bersifat esensial di belakang layar.

```python
# Di dalam _revalidate_filtered_choice_fields
if f.key == "faculty" and role in (ROLE_STUDENT, ROLE_BEM, ROLE_MABA):
    continue
```

## Hasil Verifikasi
Skrip otomatis (`test_major_logic.py`) yang mereplikasi aksi berantai: `/start` -> Pilih Fakultas -> Pilih Jurusan -> `/ubah` -> Pilih Fakultas -> Pilih Jurusan -> Disetujui Admin, telah dijalankan dan seluruh *assertion* memvalidasi bahwa field `faculty` tersimpan secara sempurna berbarengan dengan `major`.
