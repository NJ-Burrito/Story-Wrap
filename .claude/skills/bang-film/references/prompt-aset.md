# Prompt aset — gerbang 5

Keluaran gerbang ini: `epNN/prompt-aset.md`, berisi prompt untuk AI gambar. Satu judul markdown +
satu blok prompt per aset. Judul ada **di luar** blok, karena judul untuk manusia dan tidak boleh
ikut ter-copy.

Tiap aset dibuat **sekali per seri**. Karena itu `epNN/prompt-aset.md` hanya berisi aset yang
**baru muncul di episode itu**, ditambah satu baris di atas untuk yang dipakai ulang:

```markdown
Pakai ulang dari ep 01, jangan generate ulang: `adit_sheet.png`, `ruang_tengah_plate.png`.

Aset baru di episode ini: IBU.
```

Aset yang baru dibutuhkan di episode belakangan ditulis di episode tempat ia pertama muncul —
termasuk set yang hanya terlihat sekilas, misalnya ruangan yang diintip lewat celah pintu.

## Sheet karakter — tiga panel

Susunan sudah dikunci dan tidak diubah: **close-up di kiri, badan depan di tengah, badan belakang
di kanan, nama tokoh tercetak di gambar.**

````markdown
## Sheet karakter · RAFA
Simpan sebagai: `rafa_sheet.png` → token `[gambar_rafa]`

```
Character reference sheet for film production. Three panels side by side, separated by
thin subtle vertical gaps. One continuous neutral dark grey seamless studio backdrop
across all three panels. Soft even studio lighting, photorealistic cinematic
photography, 35mm film look, fine grain, muted desaturated colour.

LEFT PANEL: tight close-up portrait, head and shoulders only, neutral expression, mouth
closed, eyes looking straight into the lens, sharp focus on the eyes.

MIDDLE PANEL: the SAME person, full body head to feet, standing straight facing the
camera, head and face fully visible, arms relaxed at the sides, feet together, neutral
expression.

RIGHT PANEL: the SAME person, full body head to feet, standing straight seen from
directly behind, head fully visible, arms relaxed at the sides, showing the back of the
clothing.

THE PERSON: <bentuk panjang dari cast.md, disalin apa adanya>

WARDROBE: <baris WARDROBE dari cast.md, disalin apa adanya>

A clean white sans-serif label reading RAFA printed in the lower left corner of the left
panel.

The same person, the same face, the same clothing in all three panels. Photorealistic,
not illustration.

Avoid: more than one person per panel, different faces between panels, missing head,
patterned or gradient background, hard shadows, dramatic camera angles, extra text,
watermark, logo.
```
````

### Yang tidak boleh diubah

- **Urutan panel.** Close-up kiri, depan tengah, belakang kanan.
- **Label nama.** Tanpa nama tercetak, sheet tertukar saat dilampirkan — dan itu kesalahan yang
  paling mahal, karena baru ketahuan setelah semua klip jadi.
- **`missing head` di daftar Avoid.** Model gambar punya kecenderungan menghasilkan panel badan
  tanpa kepala kalau fokusnya ke pakaian. Baris ini mencegahnya.
- **`different faces between panels` di daftar Avoid.** Seluruh gunanya sheet ini adalah tiga
  panel menampilkan orang yang sama.
- **Latar abu netral polos.** Latar berpola membuat model ikut memakainya sebagai konteks saat
  sheet dipakai jadi referensi video.

### Yang boleh disesuaikan

- Ekspresi di panel kiri, kalau tokohnya memang punya ekspresi khas. Tetap mulut tertutup.
- Properti di tangan, kalau itu bagian dari identitas tokoh — kunci inggris, map, tongkat. Ganti
  frasa `arms relaxed at the sides` di panel tengah dan kanan, misalnya:
  `left arm relaxed at her side, right hand resting on the walking cane`.
- Rasio gambar. 16:9 nyaman untuk tiga panel. Lebih sempit dari 3:2 bikin panel badan terlalu kecil.

## Set plate

Satu per lokasi. **Tanpa orang sama sekali** — plate ini acuan ruang, bukan adegan.

````markdown
## Set plate · Ruang rapat
Simpan sebagai: `ruang_rapat_plate.png` → token `[gambar_ruang_rapat]`

```
Photorealistic interior photograph, absolutely no people in frame.

<blok set dari set.md, disalin apa adanya>

Midday, hard daylight entering from the left. 24mm lens, eye height, level horizon,
straight-on composition.

Avoid: people, text, signage, extra furniture, coloured practical lights, lens flare,
watermark.
```
````

Catatan soal lensa: pakai lensa lebar (24mm) dan horizon rata supaya seluruh ruang terbaca. Plate
ini bukan shot sinematik — tugasnya memberi tahu model bentuk ruangannya, bukan gayanya.

**Pilih sudut plate dari shot wide terpenting.** Sebagian model memperlakukan plate sebagai
pandangan kamera: shot wide kembali ke komposisi plate walau teks meminta sudut lain. Di satu uji,
motor yang diminta parkir di gang terus muncul di dalam pagar, mengikuti susunan plate teras.
Jadi kalau shot wide terpenting diambil dari seberang gang, ambil plate dari seberang gang juga.
Kalau sudut itu tidak tertulis di shot list, pakai straight-on biasa.

Lokasi luar ruang memakai `Photorealistic exterior photograph`. Tambahkan ke daftar Avoid benda
yang **memang tidak boleh ada di plate** walau nanti muncul di adegan — misalnya `packages` dan
`footprints in the dust` untuk teras yang di ceritanya selalu kosong dan berdebu. Plate adalah
keadaan dasar ruang; benda yang dibawa tokoh masuk ditulis di prompt video, bukan di plate.

## Plate properti

Hanya untuk properti **berpelat** (lihat `cast.md` bagian Properti). Properti teks saja tidak
butuh prompt di sini.

````markdown
## Plate properti · Motor
Simpan sebagai: `motor_plate.png` → token `[gambar_motor]`

```
Photorealistic reference photograph of a single vehicle, absolutely no people.

<blok properti dari set.md, disalin apa adanya>

Plain neutral grey seamless studio backdrop, soft even studio lighting. Three-quarter
front view from the right side so the scuffed panel is visible, 35mm lens, eye height,
the whole scooter in frame with space around it.

Avoid: people, rider, helmet on the seat, text, logos, brand names, licence plate
numbers, extra accessories, watermark.
```
````

Latar abu polos seperti sheet karakter, bukan di lokasi. Pilih sudut pandang yang menampilkan ciri
uniknya — goresan, penyok, warna yang pudar sebelah.

## Sheet varian wardrobe

Kalau tokoh ganti baju, buat sheet terpisah dengan token berbeda (`[gambar_rafa_b]`). Isi prompt
sama persis, hanya baris `WARDROBE` dan label nama yang berubah — label jadi `RAFA B` supaya tidak
tertukar dengan sheet aslinya.

## Catatan untuk user saat menyerahkan

Tulis satu baris di atas daftar prompt:

> Generate aset ini dulu di AI gambar mana pun. Simpan dengan nama berkas yang tertulis di tiap
> judul, karena nama itu yang dipakai sebagai token di prompt video.

Jangan menyebut model gambar tertentu. User bebas memilih.
