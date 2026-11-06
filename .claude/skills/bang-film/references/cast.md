# Cast & set bible — gerbang 3

Ini gerbang yang menentukan apakah wajah tokoh berubah-ubah atau tidak. Satu-satunya cara menjaga
konsistensi tanpa bisa menggenerate apa pun adalah memastikan **teks deskripsinya identik di mana
pun ia muncul**.

## Kenapa harus identik huruf per huruf

Model gambar dan model video memperlakukan deskripsi sebagai titik acuan. "Rambut cepak hitam"
dan "rambut pendek hitam" menghasilkan dua orang yang berbeda. Manusia tidak sanggup menulis
deskripsi yang persis sama empat puluh kali; skill ini sanggup, dan itu nilai utamanya.

Aturannya: **tulis sekali di `cast.md`, lalu salin — jangan ketik ulang, jangan diringkas, jangan
diparafrase.**

## Dua bentuk per tokoh

### Bentuk panjang — dipakai di prompt sheet karakter

Harus memuat tujuh hal ini, dalam urutan ini:

1. Kebangsaan dan jenis kelamin
2. Usia dan tinggi
3. Warna kulit
4. Rambut: panjang, warna, cara ditata
5. Bentuk wajah atau rahang
6. **Satu ciri unik yang spesifik** — bekas luka, tahi lalat, gigi gingsul, bentuk alis
7. Bangun badan

Lalu wardrobe, per item, lengkap dengan warna dan bahan.
Lalu nada tubuh: satu kalimat soal bagaimana dia berdiri dan bergerak.

```
[RAFA] — bentuk panjang
Indonesian man, 28 years old, 172 cm, warm brown skin, short cropped black hair,
strong jaw, a small 1 cm scar above his left eyebrow, lean muscular build.
WARDROBE: dark navy blue long-sleeve technician uniform shirt with the sleeves rolled
to the forearm, the name RAFA embroidered in small white letters on the right chest,
matching dark navy work trousers, black work boots, grey cloth gloves tucked into the
trouser pocket.
NADA TUBUH: tenang, pundak turun, jarang menatap mata orang lebih dari dua detik.
```

**Ciri unik nomor 6 itu jangkar utamanya.** Tanpa itu, model akan menghasilkan wajah generik yang
berubah tiap generate. Satu bekas luka kecil di tempat yang jelas jauh lebih kuat daripada lima
kata sifat.

Untuk tokoh yang punya hubungan darah, ciri unik yang **sama di tempat yang sama** bisa jadi alat
cerita — misalnya ibu dan anak sama-sama punya tahi lalat di tulang pipi kiri. Penonton mengenali
hubungan mereka sebelum ada dialog yang menyebutkannya. Kalau dipakai, tulis eksplisit di blok
CRITICAL prompt video bahwa ciri itu ada pada keduanya, supaya model tidak menganggapnya salah
salin dan tidak menggabungkan dua wajah.

Bentuk panjang ditulis dalam **bahasa Inggris** — itu bahasa prompt. Hanya baris nada tubuh yang
boleh Indonesia, karena baris itu untuk manusia, bukan untuk model.

### Bentuk pendek — dipakai di blok CHARACTERS prompt video

Satu baris. Nama, token gambar, usia, wardrobe ringkas, dan apa yang dia lakukan di scene itu.

```
RAFA [gambar_rafa] — 28, dark navy technician uniform, sleeves rolled to the forearm,
name patch on the right chest, up a step-ladder holding a wrench.
```

Deskripsi fisik lengkap **tidak diulang di sini**. Yang mengunci wajah adalah gambar sheet yang
dilampirkan user, bukan teksnya. Mengulang deskripsi panjang di prompt video justru bisa berbenturan
dengan gambar referensi.

Bagian "apa yang dia lakukan" berubah per scene. Bagian wardrobe tidak, kecuali tokoh memang ganti
baju — dan kalau ganti baju, itu wardrobe varian, lihat di bawah.

## Token gambar

Tiap tokoh dapat satu token: `[gambar_<nama kecil tanpa spasi>]`.

| Tokoh | Token | Nama berkas sheet |
|---|---|---|
| RAFA | `[gambar_rafa]` | `rafa_sheet.png` |
| BU DIAN | `[gambar_bu_dian]` | `bu_dian_sheet.png` |
| Ruang rapat (set) | `[gambar_ruang_rapat]` | `ruang_rapat_plate.png` |
| Motor (properti) | `[gambar_motor]` | `motor_plate.png` |

Polanya: `<nama>_sheet.png` untuk tokoh, `<nama>_plate.png` untuk set dan properti, dengan
`<nama>` sama persis dengan bagian token setelah `gambar_`. Pengecek gerbang 7 menolak nama yang
tidak sejalan.

**Nama token dan nama berkas harus sejalan.** User melihat token di prompt, lalu mencari berkas
dengan nama itu untuk dilampirkan. Kalau dua nama ini berbeda, user akan salah lampir dan wajahnya
tertukar — persis masalah yang skill ini ada untuk mencegah.

Lokasi juga pakai token yang sama polanya: `[gambar_ruang_rapat]`, `[gambar_lobi]`.

## Wardrobe varian

Kalau tokoh ganti baju di episode lain, jangan menimpa wardrobe lama. Tambahkan varian:

```
WARDROBE A (ep 1-3): dark navy technician uniform ...
WARDROBE B (ep 4-6): charcoal grey suit, white shirt, no tie ...
```

Tiap varian butuh sheet-nya sendiri, dan tokennya dibedakan: `[gambar_rafa_b]`. Wajahnya sama,
bajunya beda — dan model perlu melihat keduanya.

## `set.md`

Pola yang sama untuk lokasi. Yang wajib ada:

1. Jenis ruang dan di mana
2. Satu elemen arsitektur besar yang menentukan komposisi — dinding kaca, tangga, jendela tunggal
3. Furnitur utama dan jumlahnya kalau penting
4. Material lantai, karena lantai menentukan pantulan cahaya
5. **Satu benda ganjil** yang jadi penanda ruangan itu
6. **Semua pintu dan jalan masuk yang dipakai tokoh di arc** — pintu depan, ambang dapur, tangga.
   Kalau tokoh masuk lewat pintu yang tidak tertulis, model akan mengarangnya, dan pintunya
   berbeda di tiap klip.

Nomor 6 paling sering terlewat, karena di gerbang 3 blocking belum ditulis. Pikirkan arc-nya:
siapa masuk dari mana, siapa keluar ke mana. Yang masih terlewat boleh ditambahkan di gerbang 4.

```
[RUANG RAPAT] [gambar_ruang_rapat]
High-floor Jakarta office meeting room. One full-height glass wall onto layered towers.
Long wood table, twelve black mesh chairs. Grey marble floor. One ceiling cassette
air-conditioner with its access panel hanging open.
```

Benda ganjil di contoh itu adalah panel AC yang menggantung terbuka. Fungsinya dua: bikin ruangan
itu punya identitas, dan jadi alasan cerita kenapa ada teknisi di sana.

## Properti

Benda atau kendaraan yang **muncul di lebih dari satu shot** dan bisa berubah bentuk antar klip
kalau tidak dikunci: motor tokoh, mobil, tas yang selalu dibawa, foto yang muncul di dua episode.
Ditulis di bagian `## Properti` di `set.md`, dengan `###` per benda.

Dua jenis penguncian:

| Jenis | Kapan | Bentuk |
|---|---|---|
| **Berpelat** | benda besar dengan bentuk yang rumit — kendaraan, perabot khas | blok teks + token `[gambar_x]` + prompt plate di gerbang 5 |
| **Teks saja** | benda kecil dan sederhana — kardus, gelas, foto | blok teks saja, disalin identik di setiap prompt yang memuatnya |

Untuk benda yang di dunia nyata pasti bertulisan — label paket, plat nomor, merek — tulis
larangannya di dalam blok: `no labels, no printed text, no logos`, `licence plate blank`. AI video
merender tulisan jadi huruf acak yang langsung terlihat palsu.

```
[MOTOR] [gambar_motor]
Dusty black automatic scooter with a small black top box behind the seat, a scuffed
right side panel, no logos or lettering anywhere, licence plate blank.

[PAKET] — teks saja
small brown cardboard box, roughly shoebox size, wrapped in clear packing tape, no
labels, no printed text, no logos
```

Di prompt video, properti ditulis di blok **LOCATION**, setelah lokasinya.

## Saat melanjutkan episode lama

Baca `cast.md` dan `set.md` yang sudah ada. **Jangan tulis ulang.** Kalau ada tokoh baru, tambahkan
di bawah yang lama; kalau ada yang berubah bajunya, tambahkan varian. Tokoh lama yang muncul lagi
di episode baru memakai blok yang persis sama dengan sebelumnya.
