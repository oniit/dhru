# Task 148: Penambahan Keterangan Predikat pada Caption Ijazah

## Ringkasan Eksekutif
Menambahkan baris **Predikat** kelulusan pada keterangan pesan (*caption*) saat kartu Ijazah dikirimkan oleh bot melalui perintah `/ijazah` (`bot/handlers/graduation.py`).

---

## Rincian Perubahan Teknis
- Mengambil nilai `student.predikat` dari data kelulusan shishya.
- Menambahkan baris `<b>Predikat:</b> {predikat_esc}` pada template caption `cap` di handler `cmd_ijazah`.
- Jika nilai predikat kosong atau `-`, sistem memberikan fallback nilai default `"LULUS"`.
- Memperbarui dokumentasi di `docs/commands.md`.

---

## Verifikasi
- Pengujian formatting caption pada objek kelulusan menghasilkan teks:
  ```html
  🎓 <b>Ijazah Kelulusan Resmi</b>
  <b>Institut Dhruva Ekāgra</b>

  Selamat kepada <b>Aluna Valencia</b> (NIM: <code>02004010093</code>)
  <b>Program Studi:</b> Fotografi - Ilmu Budaya
  <b>Gelar:</b> Sarjana Seni (S.Sn.)
  <b>Predikat:</b> CUMLAUDE
  ```
- Tidak ada error sintaksis.

