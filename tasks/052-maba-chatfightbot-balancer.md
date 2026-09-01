# Integrasi Chat Tracker & Auto-Balancer Kelompok Maba

## Latar Belakang
Sebelumnya, sistem plotting kelompok Maba didasarkan murni pada urutan waktu (`m_order`) penebusan kode akses menggunakan algoritma Round-Robin sederhana `((m_order - 1) % 4) + 1`. Hal ini cukup untuk meratakan "tingkat responsivitas" maba ke seluruh kelompok, namun belum memperhitungkan "tingkat keaktifan/kecerewetan" mereka di grup. Diperlukan mekanisme baru untuk memastikan setiap kelompok memiliki komposisi maba aktif dan pasif yang seimbang, tanpa menghilangkan esensi adu cepat input kode.

## Perubahan yang Dilakukan
1. **Chat Tracker (Chatfightbot-lite)**: 
   - Menambahkan tabel `user_chat_stats` di `bot/database.py` untuk melacak `message_count` setiap pengguna di suatu grup.
   - Mengubah `track_group_activity` di `bot/handlers/messages.py` agar selalu menambah `message_count` setiap kali ada pesan dari pengguna biasa di grup.
   
2. **Dynamic Tiering**:
   - Membuat fungsi `get_all_users_chat_tiers` di `bot/database.py` yang menggunakan perhitungan persentil dinamis. Semua pengguna yang terlacak akan dikalkulasi persentilnya.
   - Top 33% masuk Tier A (Sangat Aktif), Middle 33% masuk Tier B (Normal), Bottom 33% masuk Tier C (Pendiam).

3. **Tiered Round-Robin + Balancer**:
   - Menghapus logika Round-Robin lama untuk `target_role == 'maba'`.
   - Mengubah logika menjadi: 
     1. Ambil seluruh data anggota maba yang sudah diplot.
     2. Hitung jumlah maba di setiap grup untuk Tier yang sama dengan pengguna saat ini (Prioritas 1: Keseimbangan Keaktifan).
     3. Pilih grup yang memiliki anggota dengan Tier tersebut paling sedikit.
     4. Jika ada hasil imbang, gunakan *Balancer* (Prioritas 2: Keseimbangan Kuantitas) dengan memilih grup yang total jumlah anggotanya paling sedikit secara keseluruhan.

## Kesimpulan
Logika plotting kini mempertimbangkan total riwayat chat maba secara dinamis. Hasil pembagian kelompok akan selalu memiliki komposisi keaktifan yang setara, namun dengan total kepala akhir yang seimbang antar kelompok.
