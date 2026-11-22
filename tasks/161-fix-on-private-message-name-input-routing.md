# Task 161: Perbaikan Routing Input Nama dan Pesan Privat (on_private_message)

## Latar Belakang & Masalah
Pengguna melaporkan kendala saat membuat akun baru:
> "gw coba bikin akun baru niatnya mau tes utk purna ke free pass itu. eh ternyata gabisa isi nama dll, coba jd publik jg gabisa isi, gada balesan gitu ketika disuruh isi nama"

Ketika pengguna baru menjalankan `/start` lalu memilih "👤 Daftar Akun Publik" atau menjalankan `/lengkapi` dan menekan tombol pengisian nama ("✏️ Nama Lengkap"), bot meminta pengguna mengetikkan nama lengkap (`Kirim pesan teks untuk Nama Lengkap (lengkapi)`). Namun ketika pengguna mengetikkan dan mengirimkan namanya di chat privat, bot **tidak membalas sama sekali** dan data nama tidak tersimpan.

## Analisis Akar Masalah (Root Cause)
Setelah dilakukan investigasi menyeluruh (*holistic debugging*) pada berkas `bot/handlers/messages.py`:
1. **Kesalahan Penempatan & Pemotongan Fungsi `on_private_message`**:
   - Fungsi `handle_input_code` (yang menangani input kode akses & warkat kehormatan) sebelumnya dideklarasikan tepat di baris 406 (`async def handle_input_code(...)`) pada indentasi kolom 0 di tengah-tengah badan fungsi `on_private_message`.
   - Akibat deklarasi fungsi baru di kolom 0 tersebut, Python menganggap fungsi `on_private_message` telah selesai/berakhir di baris 404 (setelah blok penanganan soal charyarthi).
   - Seluruh baris logika setelah baris 406 (termasuk penanganan `step == "INPUT_CODE"`, `STEP_KARTU_PHOTO`, `TUGAS_JUDUL`, `TUGAS_INPUT`, `TUGAS_TOLAK`, `ADMIN_TEXT_LC`, dan yang paling utama: `TEXT_LC:` dan `TEXT_EC:`) menjadi terindentasi dan terperangkap sebagai bagian internal dari `handle_input_code`!
2. **Dampak Langsung**:
   - Setiap kali pengguna mengirimkan pesan teks privat dengan step `TEXT_LC:full_name` (atau field profil lainnya), eksekusi masuk ke `on_private_message`.
   - Karena `on_private_message` terpotong di baris 404, tidak ada blok `if` yang cocok, fungsi selesai dengan nilai `None`, dan bot tidak memberikan respons apa pun.

## Solusi & Perbaikan Teknis
1. **Pemindahan `handle_input_code` ke Level Modul Independen**:
   - Memindahkan definisi fungsi `handle_input_code` secara utuh ke sebelum fungsi `on_private_message` (di baris 116).
   - Menghapus deklarasi ganda di tengah fungsi `on_private_message`.
2. **Restorasi Kelengkapan `on_private_message`**:
   - Seluruh penanganan `step` (mulai dari `INPUT_CODE`, pengiriman foto kartu, pengumpulan tugas, hingga pengisian field `TEXT_LC:` dan pengajuan `/ubah` pada `TEXT_EC:`) kini kembali utuh menjadi satu rantai eksekusi di dalam `on_private_message`.
3. **Pengujian Unit & QA Audit**:
   - Menambahkan unit test `test_on_private_message_text_lc_full_name` pada `tests/test_warkat.py` untuk memvalidasi alur pengisian nama lengkap publik via `TEXT_LC:full_name`.
   - Seluruh 47 pengujian unit lulus 100%.
   - Seluruh 93 pengujian pada Master QA Audit (`tests/test_qa_master_audit.py`) lulus 100%.
