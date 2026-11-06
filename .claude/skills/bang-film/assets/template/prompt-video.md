<!-- Pengisian (hapus komentar ini setelah diisi): durasi tiap scene 4–30 detik; baris SCENE
tanpa nomor dan timecode mulai 00:00; MOVEMENT NOTE selalu ada — satu tokoh berisi nada tubuh,
lebih dari dua orang wajib memecah figuran; properti ditulis di LOCATION; scene tanpa dialog
memakai LANGUAGE bentuk "This scene has NO spoken dialogue". CONTINUITY opsional — hapus kalau
tidak ada benda yang harus bertahan antar potongan. Lebih dari satu plate lokasi dalam satu
generate: peta referensi di awal LOCATION, tag lokasi di tiap SHOT, dan CONTINUITY wajib. -->


# Prompt video — Ep <NN> · <judul episode>

Generate per scene. Lampirkan berkas yang disebut di tiap judul sebagai referensi gambar, lalu
atur rasio dan durasi di pengaturan AI video sebelum generate.

---

## Scene 1 · <lokasi> · <n> detik
Lampirkan: `<nama>_sheet.png`, `<nama>_plate.png`

```
VIDEO STYLE & FORMAT
<n>-second scene in the style of <jenis tontonan>. ONE continuous <apa> — <deskripsi>,
NOT a trailer, NOT a montage — covered like a real film: cut between MULTIPLE camera
positions, angles changing every few seconds while the story flows continuously.
<tempo>. <gaya akting>. Look: <grading, grain, depth of field, skin tone, cahaya>.
NOT <yang dihindari>, NO <yang dihindari>, dialogue never rushed.

LANGUAGE
All spoken dialogue in <BAHASA> only, <register>. Speak the lines exactly as written in
the breakdown below: do not translate them, do not paraphrase them, do not invent extra
lines. Numbers are spoken as <bahasa> words. No subtitles, no captions, no on-screen text
of any kind burned into the frame. Character names are never spoken aloud unless they
appear inside the quotation marks.

OPTICS
Base <n>mm spherical at T<n> — <perspektif>, <kompresi>, <depth of field>. Close-ups step
up to <n>mm (FOV approx <n> degrees) for <alasan>. Per-shot lens is specified in the
breakdown. No wide-angle distortion, no fisheye, no zoom moves.

CAMERA
Every cut moves to a DIFFERENT physical position — <daftar posisi>. Never two consecutive
shots from the same position. Movement is limited to <jenis gerakan>; no <yang dilarang>.
No slow-motion.

LIGHTING
<sumber utama>, <arah>, <kualitas>. <sisi gelap dan negative fill>. <suhu warna>;
the only <hangat/dingin> note is <satu aksen tunggal>. <low-key atau high-key>, never flat
front light. <pantulan dari lantai atau permukaan>.

CRITICAL
<jumlah> speaking characters plus <jumlah> background. Every character keeps the exact
face, hairstyle and clothing from their reference images in every shot. No face swapping,
no morphing, no duplicated faces, no extra people appearing or vanishing between cuts.
Accurate <bahasa> lip-sync — only the speaking character's mouth moves; everyone else
stays still and listens.

CHARACTERS (from reference images)
<NAMA> [gambar_<nama>] — <bentuk pendek dari cast.md>
BACKGROUND — <deskripsi figuran, jumlahnya, none featured>.

LOCATION (from references)
<peta referensi — hanya kalau lebih dari satu plate lokasi: plate mana, sisi mana, SHOT berapa>
<nama lokasi> [gambar_<nama>] — <blok set dari set.md>
<properti berpelat> [gambar_<nama>] — <blok properti dari set.md>
<properti teks saja> — <blok properti dari set.md>

CONTINUITY
People and objects persist between cuts exactly where they were left. Nothing appears or
disappears between cuts unless <tokoh> moves it on screen.
- <NAMA TOKOH>: <di mana dia sepanjang scene, dan ke mana dia tidak pernah pergi>.
- <BENDA>: <tempat persisnya, sejak SHOT berapa>. It is visible in <SHOT yang
  memperlihatkannya>; in the other shots it is outside the frame — never gone.

AUDIO
<ambience>. <suara spesifik>. <skor: ada, tidak ada, atau masuk di detik berapa>.
Dialogue in natural <bahasa> at <tempo>, with real silence between lines.

MOVEMENT NOTE
<tokoh A> and <tokoh B> run on OPPOSITE rhythms. <ritme A>. <ritme B>. The <jumlah>
background NEVER react as a block — <tiga reaksi berbeda>; never a synchronised crowd turn.

SHOT BREAKDOWN

SCENE [00:00-00:<nn>] <LOKASI> — one continuous <apa>, cut between positions:

SHOT 1 (0-<n>s), <n>mm <UKURAN> from <posisi>, <gerakan>: <aksi>.
<lokasi ganda: SHOT 1 (0-<n>s) — <SISI>, <tempat>, <dilihat dari mana> — <n>mm <UKURAN> ...>

<NAMA> (<arahan intonasi>): "<dialog>"

SHOT 2 (<n>-<n>s), <n>mm <UKURAN> from <posisi berbeda>, <gerakan>: <aksi>. No dialogue —
<n> seconds of <ambience>.

The shot ends <pada gerakan apa> — no freeze frame, no fade to black.
```

---

## Scene 2 · <lokasi> · <n> detik
Lampirkan: `...`

```
...
```
