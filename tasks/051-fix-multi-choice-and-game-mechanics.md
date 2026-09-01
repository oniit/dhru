# Task 051: Fix Multi-Choice UI and Game Mechanics

## Apa yang Dikerjakan
1. **Perbaikan Bug Multi-Choice (UnboundLocalError):**
   - Menghapus import *inline* dari `user_row`, `profile_from_row`, dan `ROLE_MABA` di dalam fungsi `on_callback` (tepatnya pada *handler* `claim_ospek`).
   - Import *inline* tersebut menyebabkan *shadowing* variabel lokal oleh *compiler* Python untuk keseluruhan fungsi `on_callback`, yang mengakibatkan semua *handler* *multi-choice* (`mec:`, `mlc:`, `admlc:`, dll) mengalami *crash* saat mencoba memanggil `user_row(...)`.
2. **Pembaruan Mekanik Game Tujuh Pusaka:**
   - **Kartu Neil:** Efek -20 Str pada ronde berikutnya ketika bot menang dengan menggunakan Neil sekarang diisolasi per-pemain menggunakan atribut *dictionary* `bot_next_round_penalty` khusus pemain yang bersangkutan, sehingga tidak berdampak secara global ke semua pemain di ronde selanjutnya.
   - **Sistem Hangus/Timeout:** Saat pemain melewati batas waktu (*skip*) tanpa memilih kartu, bot sekarang akan memilih satu kartu secara acak dari tangan pemain tersebut untuk dihapus (hangus) dan menambahkan notifikasi ke hasil ronde.

## Mengapa Dikerjakan
- Bug profil membuat *user* (terutama panel admin/onboarding) sama sekali tidak bisa menekan tombol *multi-choice* dengan baik karena selalu me-lempar *exception* tersembunyi (*silenced* secara default jika tidak ditangkap manual ke *console* Telegram).
- Mekanisme Tujuh Pusaka sebelumnya menyebabkan keuntungan/kerugian di luar kewajaran karena efek negatif dari satu kartu berlaku merata ke duel dengan *player* lain. Mekanisme *skip* yang baru (membakar kartu) juga lebih menghukum perilaku *AFK* pemain, mencegah mereka membuang ronde demi menyisakan kartu kuat di akhir ronde.

## Cara Kerja secara Teknis
- **Bug Fix:** Python sudah memuat `user_row` dan fungsi lain secara *global* di bagian atas *file* `bot/handlers/commands.py`. Penghapusan deklarasi lokal memastikan interpreter Python menggunakan referensi dari *module global*.
- **Penalty Isolasi:** Modifikasi dilakukan pada struktur *state* `tujuh_pusaka.py`, menggantikan `bot_next_penalty` yang bersifat tunggal di level *root* sesi menjadi tersimpan di dalam iterasi *loop* pemain: `state["players"][uid]["bot_next_round_penalty"]`.
- **Card Burn Logic:** Jika `uid_str not in state["choices"]` dan kartu pemain masih tersisa, fungsi `random.choice(p_data["cards"])` dipanggil dan disusul operasi `remove()`. Hal ini secara dinamis memperkecil pasokan kartu pemain, membuat pemain tidak memiliki amunisi di babak akhir permainan.
