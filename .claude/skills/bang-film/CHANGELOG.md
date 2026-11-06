# Changelog

## 1.2.0 — 2026-10-31

**Pelajaran dari empat uji generate sungguhan.** Satu scene microdrama — tujuh shot, dua plate lokasi
dalam satu generate — di-generate empat kali dengan prompt yang diperbaiki bertahap, lalu dibedah per
shot: titik potong, lembar kontak, dan transkrip dialog.

- Blok opsional `CONTINUITY` di antara LOCATION dan AUDIO: posisi tokoh, dan benda yang harus bertahan
  antar potongan.
- Peta referensi di awal LOCATION dan tag lokasi di tiap baris SHOT — wajib kalau satu generate memakai
  lebih dari satu plate lokasi. Tanpa itu tokoh bocor ke sisi pintu yang salah.
- Shot lewat celah atau kaca hanya menulis apa yang terlihat; ketiadaan benda ditulis sebagai permukaan
  rata; benda tidak ditegaskan berulang-ulang.
- Tabel shot berisiko di gerbang 4 (`references/konsep.md`, bagian baru di `naskah.md`): tujuh faktor
  rawan plot hole, alternatifnya, dan keputusan user.
- Memperbaiki prompt setelah generate (`references/verifikasi.md`): bedah dulu, satu-dua kalimat per
  masalah, simpan versi baru, kembali kalau memburuk. Tujuh gejala baru di tabel gejala → penyebab.
- Tips sudut plate di `references/prompt-aset.md`: ambil plate dari sudut shot wide terpenting.
- `check_prompts.py` menerima CONTINUITY dan menolak prompt berlokasi ganda tanpa tag, peta, atau
  CONTINUITY.
- Contoh `alamat-yang-sama` ep 01 memakai bentuk baru, dan `naskah.md`-nya mencatat shot berisiko.

## 1.1.0 — 2026-10-31

**Hasil uji jalan dengan proyek "Alamat yang Sama"** — microdrama 3 episode × 30 detik.

- Brief jadi dua kartu, karena alat tanya maksimal empat pertanyaan. Jawaban yang saling bentrok
  disebutkan ke user, tidak dipilih diam-diam.
- Satu prompt video = satu generate = 4–30 detik. Episode yang lebih panjang dipecah mengikuti alur.
- Beat penting tidak boleh bergantung pada tulisan di layar.
- Properti berulang (kendaraan, paket, foto) dikunci seperti tokoh, ditulis di LOCATION, boleh berpelat.
- Blok set wajib memuat semua jalan masuk yang dipakai arc; gerbang 4 boleh menambah elemen set.
- MOVEMENT NOTE selalu ada; baris SCENE tanpa nomor; rubrik ditambah baris Konsisten dan Tanpa teks.
- `assets/tools/check_prompts.py`: pengecek gerbang 7, Python 3 tanpa dependensi.
- Contoh proyek lengkap `assets/contoh/alamat-yang-sama/`.

## 1.0.0 — 2026-10-31

Rilis pertama. Tujuh gerbang dengan tiga persetujuan, tiga preset (microdrama, short movie,
scene/trailer), cast bible bentuk panjang dan pendek, sheet karakter tiga panel dengan nama tercetak di
gambar, prompt video sebelas blok yang ditulis general untuk AI video mana pun, template, dan contoh
seri "Unit 7".
