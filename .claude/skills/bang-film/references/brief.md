# Brief — gerbang 1

Tujuan gerbang ini: mengunci parameter yang **tidak bisa diturunkan dari topik**. Semua angka di
sini milik user. Skill tidak punya pendapat soal angka.

## Aturan inti

1. **Jangan pernah mengisi sendiri.** Tidak ada default rasio, default durasi, default jumlah
   episode. Kosongkan, biarkan user yang menjawab.
2. **Dua kartu, tidak lebih.** Alat tanya pilihan maksimal empat pertanyaan per kartu, jadi brief
   dibagi persis dua kartu (lihat tabel di bawah). Jangan mencicil sisanya di pesan teks.
3. **Jangan tanya jumlah shot.** Lihat bagian "Yang tidak ditanyakan" di bawah.
4. Topik cerita boleh diturunkan dari kalimat pertama user. Kalau user sudah bilang "microdrama
   tentang teknisi AC", formatnya sudah terjawab — jangan tanya ulang, tandai saja sebagai
   terisi dan tanyakan sisanya.

## Daftar pertanyaan

| Kartu | Pertanyaan | Opsi yang ditawarkan | Catatan |
|---|---|---|---|
| 1 | **Topik** | 2–3 ide konkret + isi sendiri | dilewati kalau user sudah menyebut cerita |
| 1 | **Format** | Microdrama seri · Short movie · Scene/trailer tunggal | menentukan struktur naskah di gerbang 2 dan 4 |
| 1 | **Rasio** | 9:16 · 16:9 · 1:1 | dicatat untuk user, **tidak masuk prompt** |
| 1 | **Bahasa dialog** | Indonesia · English | masuk blok `LANGUAGE` di prompt video |
| 2 | **Durasi** | 2–3 angka dengan konsekuensinya + isi sendiri | per episode kalau seri, total kalau short movie |
| 2 | **Jumlah episode** | 2–3 angka + isi sendiri | hanya untuk format seri; 1 juga sah |
| 2 | **Look** | 2–3 look yang cocok dengan topik + jelaskan sendiri | masuk blok `VIDEO STYLE & FORMAT` dan `LIGHTING` |

Alat tanya selalu menyediakan isian bebas, jadi opsi angka di kartu 2 hanyalah tawaran — user
sering mengisi angka lain, dan itu yang dipakai.

Untuk **Scene/trailer tunggal**, pertanyaan jumlah episode dilewati, dan look boleh naik ke
kartu 1.

**Durasi lebih dari 30 detik** tidak masalah — satu prompt video memang dibatasi 4–30 detik, tapi
pemecahannya dikerjakan di gerbang 4 mengikuti alur cerita. Jangan membatasi durasi episode di sini.

## Yang tidak ditanyakan

**Jumlah shot.** Shot muncul dari naskah: berapa sudut yang dibutuhkan untuk menceritakan adegan
itu. Memaksakan angka di depan membuat naskah kaku — adegan dipotong atau dipanjangkan hanya
untuk memenuhi angka. Biarkan naskah yang menentukan, lalu AI video yang mengeksekusinya.

Kalau user bertanya "berapa shot nanti?", jawab apa adanya: ditentukan setelah naskah jadi, dan
akan terlihat di shot list gerbang 4.

## Kalau user menjawab "terserah"

Jangan memaksa, tapi jangan juga diam-diam memilih sendiri lalu menuliskannya sebagai keputusan
user. Tawarkan **dua kemungkinan konkret dengan konsekuensinya**, lalu biarkan user menunjuk:

> Durasi 60 detik bikin ceritanya padat, satu beat saja — cocok kalau mau orang langsung
> nonton ulang. 90 detik kasih ruang buat satu hening sebelum cliffhanger. Pilih yang mana?

Kalau user tetap bilang terserah, pilih satu, **sebut jelas bahwa itu pilihanmu**, dan catat di
`brief.md` sebagai `(dipilih skill, belum dikonfirmasi)` supaya gampang diubah nanti.

## Kalau jawaban saling bentrok

Jawaban bisa bertabrakan satu sama lain — topik yang berbunyi "tiap malam" dengan look "siang
hari", atau durasi 15 detik untuk short movie tiga babak. Jangan diam-diam memilih salah satu.

1. Sebutkan bentroknya dalam satu kalimat.
2. Tawarkan resolusi yang paling masuk akal, dengan alasannya.
3. Catat keputusan dan alasannya di `brief.md` bagian "Penyesuaian".

Kalau resolusinya jelas dan kecil, boleh langsung jalan dengan menyebutkannya — tidak perlu
berhenti menunggu jawaban. Kalau resolusinya mengubah cerita, tanyakan.

## Mengubah brief di tengah jalan

Kalau user bilang "episode 4 jadiin 2 menit" atau "ganti ke 16:9", yang diedit **hanya
`brief.md`**. Lalu periksa dampaknya:

| Yang berubah | Perlu ditulis ulang |
|---|---|
| Rasio | tidak ada — rasio tidak pernah masuk prompt |
| Durasi | shot list, pembagian scene, dan timecode di `SHOT BREAKDOWN` |
| Jumlah episode | arc di `konsep.md` |
| Bahasa | blok `LANGUAGE` dan semua baris dialog |
| Look | blok `VIDEO STYLE & FORMAT` dan `LIGHTING` |

Sebutkan daftar dampaknya ke user sebelum mengerjakan, supaya dia tahu seberapa besar
perubahannya.

## Bentuk `brief.md`

```markdown
# Brief — <judul proyek>

| | |
|---|---|
| Format | Microdrama seri |
| Rasio | 9:16 |
| Durasi | 75 detik per episode |
| Jumlah episode | 6 |
| Bahasa dialog | Indonesia |
| Look | Jakarta modern, kantor kelas atas |

Topik: <kalimat asli user, apa adanya>

Catatan: rasio dicatat di sini untuk pengaturan AI video. Rasio tidak ditulis di dalam prompt.
```

Simpan kalimat asli user apa adanya. Nanti di gerbang 2 kalimat itu yang jadi bahan logline, dan
sering ada detail kecil di sana yang kalau diparafrase jadi hilang.
