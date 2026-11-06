# Prompt video — gerbang 6

Berkas terpenting di skill ini. Keluarannya `epNN/prompt-video.md`.

## Batas durasi

**Satu blok prompt = satu kali generate = 4–30 detik.** AI video sekarang menerima minimal 4 detik
dan maksimal 30 detik per generate. Pembagian episode jadi scene dikerjakan di gerbang 4 — lihat
`konsep.md` bagian pemecahan scene. Di gerbang ini, tiap blok tinggal mengikuti pembagian itu.

## Bentuk berkas

Satu judul markdown + satu blok prompt, **per scene**. Judul dan catatan referensi ada di luar
blok karena itu untuk manusia; yang di dalam blok adalah satu-satunya yang di-copy user.

````markdown
## Scene 1 · Ruang rapat · 30 detik
Lampirkan: `rafa_sheet.png`, `bu_dian_sheet.png`, `ruang_rapat_plate.png`

```
VIDEO STYLE & FORMAT
...
```

## Scene 2 · Basement parkir · 25 detik
Lampirkan: `rafa_sheet.png`, `basement_plate.png`

```
VIDEO STYLE & FORMAT
...
```
````

**Jangan pernah menulis header seperti `=== PROMPT VIDEO · EP01 · SCENE 1 ===` di dalam blok.**
Model tidak memahaminya dan bisa membacanya sebagai bagian adegan — misalnya menampilkan teks itu
di layar.

## Sebelas blok, berurutan

Urutannya disengaja: semua aturan dulu, baru adegan. Model membaca bagian atas sebagai batasan
untuk seluruh klip.

Ada satu blok **opsional**, `CONTINUITY`, yang kalau dipakai ditulis di antara `LOCATION` dan
`AUDIO`. Kapan dipakai — lihat bagiannya di bawah.

### 1 · VIDEO STYLE & FORMAT

Menetapkan jenis tontonan, panjang, tempo, gaya akting, dan look. Wajib memuat penegasan bahwa ini
**satu cerita berkelanjutan yang diliput dari banyak sudut**, bukan trailer dan bukan montase —
tanpa itu, model memotong jadi potongan-potongan tak nyambung.

```
VIDEO STYLE & FORMAT
30-second scene in the style of a modern Indonesian short drama. ONE continuous
confrontation — a single unbroken moment in one room, NOT a trailer, NOT a montage —
covered like a real film: cut between MULTIPLE camera positions, angles changing every
few seconds while the moment flows continuously. Slow, heavy pacing with real silence
between lines. Naturalistic acting, underplayed, never theatrical. Look: cold filmic
colour grading, crushed blacks, fine film grain, shallow depth of field, accurate
Indonesian skin tones. NOT sinetron, NO dramatic zooms, NO rapid cutting, dialogue
never rushed.
```

Durasi **tetap disebut** di sini, karena timecode di `SHOT BREAKDOWN` tidak berarti tanpanya.
Rasio **tidak** disebut, termasuk kata `vertical` dan `horizontal`.

Baris `NOT ...` di akhir penting. Sebut yang khas dan harus dihindari — untuk konteks Indonesia,
`NOT sinetron` menahan model dari zoom mendadak dan akting berlebihan.

Sebut juga **genre yang bukan**, kalau premisnya bisa disalahbaca. Rumah kosong, orang mengintip
lewat celah pintu, perempuan tua yang muncul diam-diam — model akan membacanya sebagai horor
kecuali dilarang: `This is a quiet family drama, NOT horror and NOT a thriller.`

### 2 · LANGUAGE

Blok yang paling sering dilupakan dan paling menentukan apakah dialognya keluar benar.

```
LANGUAGE
All spoken dialogue in INDONESIAN (Bahasa Indonesia), Jakarta register, casual spoken
form — not formal news-reader Indonesian. Speak the lines exactly as written in the
breakdown below: do not translate them, do not paraphrase them, do not invent extra
lines. Numbers are spoken as Indonesian words. No English words. No subtitles, no
captions, no on-screen text of any kind burned into the frame. Character names are never
spoken aloud unless they appear inside the quotation marks.
```

Enam hal yang wajib ada:
1. Bahasa apa, ditulis kapital.
2. Register — lisan atau baku, daerah mana.
3. **Ucapkan persis seperti tertulis** — jangan terjemahkan, jangan parafrase, jangan tambah baris.
4. Angka diucapkan sebagai kata.
5. Tidak ada subtitle, caption, atau teks di layar.
6. Nama tokoh tidak diucapkan kecuali memang ada di dalam tanda kutip.

Nomor 5 adalah satu-satunya tempat kata "subtitle" boleh muncul di seluruh skill ini, dan justru
sebagai larangan.

**Scene tanpa dialog** tetap memakai blok ini, dengan bentuk lain:

```
LANGUAGE
This scene has NO spoken dialogue — no voices, no narration, no inner monologue, no
whispering. No subtitles, no captions, no on-screen text of any kind burned into the
frame.
```

Tanpa blok ini, sebagian model menambahkan narasi atau gumaman sendiri.

Kalau ada suara yang bukan tokoh — notifikasi aplikasi, pengumuman, radio — sebut di sini siapa
saja yang bersuara, dan tulis barisnya di `SHOT BREAKDOWN` seperti dialog biasa:
`PHONE VOICE (off-screen, flat, synthetic): "Pesanan baru. Alamat yang sama."`

### 3 · OPTICS

Lensa dasar untuk scene, lalu lensa khusus untuk close-up. Lensa per shot ditulis lagi di dalam
`SHOT BREAKDOWN`.

```
OPTICS
Base 35mm spherical at T2.0 — natural perspective, mild compression, SHALLOW depth of
field so the twelve seated staff fall soft behind the two leads. Close-ups step up to
85mm (FOV approx 24 degrees) for face isolation and background separation. Per-shot lens
is specified in the breakdown. No wide-angle distortion, no fisheye, no zoom moves.
```

Panduan lensa:

| Lensa | FOV | Rasa |
|---|---|---|
| 24mm | ~74° | ruang terasa luas, tokoh kecil di dalamnya, perspektif melebar |
| 35mm | ~54° | perspektif natural, lensa serba guna untuk adegan dialog |
| 50mm | ~40° | netral, dekat dengan penglihatan mata |
| 85mm | ~24° | wajah terisolasi, latar lembut |
| 135mm | ~15° | kompresi kuat, jarak emosional |
| 200mm | ~12° | kompresi berat, latar hampir rata, terasa mengintip |

Sebutkan juga bukaan (T2.0, T2.8) kalau kedalaman ruang penting.

### 4 · CAMERA

Aturan perpindahan posisi dan jenis gerakan.

```
CAMERA
Every cut moves to a DIFFERENT physical position — far end of the table, behind the
seated staff at shoulder height, low beside the step-ladder, reverse on Bu Dian. Never
two consecutive shots from the same position. Movement is limited to very slow pushes on
a dolly; no handheld shake, no orbit, no crane. No slow-motion.
```

Wajib ada: daftar posisi fisik yang dipakai, dan kalimat **"never two consecutive shots from the
same position"**. Itu satu baris yang paling membedakan hasil yang terasa difilmkan dari hasil
yang terasa dibuat AI.

Sebutkan juga rig-nya: dolly, handheld, statis, breathing handheld. Kalau tokoh menatap seseorang
di luar frame, sebutkan aturan eyeline — misalnya *their eyelines sit just beside and slightly
above the lens, never into the lens*.

### 5 · LIGHTING

Bukan kata sifat. Sebutkan sumbernya, arahnya, suhu warnanya, kontrasnya.

```
LIGHTING
Single hard key: midday sun through the full-height glass wall camera-left, undiffused —
a hot white edge down the left side of every face. The ceiling fluorescent panels are OFF
because the air-conditioner is being serviced, so the right side of each face falls into
true negative fill, deep and uncorrected. Cool daylight field at 5600K; the only warm
note is one amber desk lamp at the far end of the table. Low-key, high contrast, never
flat front light. The grey marble floor bounces a thin cold sheen up onto chins.
```

Lima hal yang wajib ada:
1. **Sumber** — matahari lewat jendela, fluorescent plafon, lampu meja, layar HP, lampu jalan.
2. **Arah** — camera-left, dari atas, dari belakang, dari bawah.
3. **Suhu warna** — 3200K hangat, 5600K siang, cyan-teal dingin.
4. **Kontras dan negative fill** — low-key atau high-key, sisi gelap dibiarkan atau diisi.
5. **Satu aksen warna tunggal** — satu lampu hangat di lautan dingin, atau sebaliknya. Ini yang
   bikin frame terasa dirancang.

`dramatic lighting` tanpa menyebut sumber tidak memberi informasi apa pun ke model. Jangan dipakai.

### 6 · CRITICAL

Aturan konsistensi. Selalu ada, kalimatnya hampir selalu sama.

```
CRITICAL
TWO speaking characters plus twelve silent background staff. Every character keeps the
exact face, hairstyle and clothing from their reference images in every shot. No face
swapping, no morphing, no duplicated faces, no extra people appearing or vanishing
between cuts. Accurate Indonesian lip-sync — only the speaking character's mouth moves;
everyone else stays still and listens.
```

Sebut jumlah tokoh bicara dan jumlah figuran secara eksplisit. Model cenderung menambah orang
antar potongan kalau jumlahnya tidak dikunci. Kalau hanya satu tokoh, tulis `ONE character only.
Nobody else appears at any point` — lorong dan jalan yang mestinya sepi sering diisi orang lewat.

Benda berlayar — HP, laptop, TV — tulis `screen always angled away from camera, no readable
screen`. Layar yang menghadap kamera akan diisi tulisan acak.

### 7 · CHARACTERS

Bentuk pendek dari `cast.md`, satu baris per tokoh, dengan token gambar.

```
CHARACTERS (from reference images)
RAFA [gambar_rafa] — 28, dark navy technician uniform, sleeves rolled to the forearm,
name patch on the right chest, up a step-ladder holding a wrench.
BU DIAN [gambar_bu_dian] — 45, cream blazer over a white blouse, hair in a tight bun,
thin metal-framed glasses, standing with her arms folded.
BACKGROUND — twelve office staff in muted office wear, seated, silent, none featured.
```

Deskripsi fisik lengkap tidak diulang di sini. Gambar referensi yang mengunci wajah.

### 8 · LOCATION

```
LOCATION (from references)
The meeting room [gambar_ruang_rapat] — High-floor Jakarta office meeting room. One
full-height glass wall onto layered towers. Long wood table, twelve black mesh chairs.
Grey marble floor. One ceiling cassette air-conditioner with its access panel hanging open.
```

Blok set dari `set.md` disalin **apa adanya** setelah tanda pisah — jangan diringkas.

**Properti** ditulis di blok ini juga, setelah lokasinya. Properti berpelat memakai token,
properti teks saja tidak:

```
Adit's scooter [gambar_motor] — Dusty black automatic scooter with a small black top box
behind the seat, a scuffed right side panel, no logos or lettering anywhere, licence
plate blank.
The package — small brown cardboard box, roughly shoebox size, wrapped in clear packing
tape, no labels, no printed text, no logos
```

Lokasi yang hanya terlihat sekilas — misalnya ruangan yang diintip lewat celah pintu di shot
terakhir — tetap ditulis dan dilampirkan, dengan keterangan kapan ia terlihat:
`The living room, SHOT 7 only [gambar_ruang_tengah] — ...`

#### Peta referensi — kalau ada lebih dari satu lokasi dalam satu generate

Dua plate lokasi dalam satu prompt — ruangan yang diintip lewat celah, atau tempat yang sama dari
dua sisi pintu — membuat model tidak tahu plate mana berlaku di shot mana. Akibatnya tokoh "bocor"
ke sisi lain: kurir yang mestinya di teras tiba-tiba berdiri di dalam rumah.

Buka blok LOCATION dengan peta: plate mana, sisi mana, shot berapa. Setelah itu baru blok set
seperti biasa.

```
LOCATION (from references)
Two of the reference images show the SAME house from the two opposite sides of the SAME
frosted sliding door:
- [gambar_teras] is the OUTSIDE — the terrace, the fence, the lane. SHOTS 1 to 6 all
  happen here, outside the house.
- [gambar_ruang_tengah] is the INSIDE — the living room. It is used ONLY in SHOT 7, and
  only as seen from floor level through the gap under the door. No other shot shows the
  inside of the house.
Whenever the sliding door appears in SHOTS 1 to 6, it is seen from OUTSIDE.
The terrace [gambar_teras] — ...
```

Pasangannya ada dua: **tag lokasi** di tiap baris SHOT (lihat `SHOT BREAKDOWN`) dan **posisi
tokoh** di `CONTINUITY`. Ketiganya dipakai bersama — satu saja tidak cukup.

### CONTINUITY — opsional

Dipakai kalau scene punya:
- **lebih dari satu referensi lokasi** — wajib, untuk mengunci posisi tokoh;
- **benda yang harus bertahan antar potongan** — kendaraan yang diparkir, paket yang ditaruh,
  gerbang yang dibiarkan terbuka.

Scene dialog di satu ruangan tanpa properti yang berpindah tidak membutuhkannya.

```
CONTINUITY
People and objects persist between cuts exactly where they were left. Nothing appears or
disappears between cuts unless Adit moves it on screen.
- ADIT: outside the house for the WHOLE scene — in the lane or on the terrace. He never
  opens the sliding door and never steps inside.
- THE SCOOTER: from SHOT 2 to the end of the scene it stays parked IN THE LANE, directly
  in front of the gate, on the far side of the fence from the house. It is visible in
  every shot that looks toward the lane (SHOT 2 and SHOT 4); in the other shots it is
  behind the camera or outside the frame — never gone.
- THE PACKAGE: Adit carries it from SHOT 2 to SHOT 4. From SHOT 4 to the end of the scene
  it sits on the terrace floor, one step to the left of the sliding door.
```

Satu butir per tokoh atau benda: **di mana persisnya, sejak shot berapa, di shot mana ia
terlihat**, dan bahwa di shot lain ia hanya di luar frame. Kalimat terakhir itu yang mencegah
benda hilang setelah potongan.

Tulis sekali, dengan kalimat sederhana, lalu berhenti. **Jangan menumpuk penegasan.** Benda yang
terus-menerus disebut justru menjadi pegangan model untuk berbuat sesuatu — pintu yang ditegaskan
*stays closed* di tiga tempat malah dibuka. Maksimal tiga benda; lebih dari itu, kurangi benda di
naskah.

### 9 · AUDIO

Ambience, skor, dan catatan dialog. Hening juga ditulis — hening yang disengaja berbeda dari
audio yang lupa diisi.

```
AUDIO
Room tone of a sealed high-floor office with the air-conditioning OFF — no hum, noticeably
dead. Faint traffic far below the glass. A wrench set down on aluminium. Chair fabric
shifting. NO musical score at all until the final two seconds, then one low sustained
cello note. Dialogue in natural Indonesian at an unhurried pace, with real silence between
lines.
```

### 10 · MOVEMENT NOTE

**Selalu ada.** Isinya tergantung jumlah orang di frame:

| Di frame | Isi MOVEMENT NOTE |
|---|---|
| Satu tokoh | nada tubuhnya dari `cast.md` — cara berdiri, cara bergerak, apa yang tidak pernah dia lakukan |
| Dua tokoh | dua ritme yang berlawanan, tidak pernah cermin |
| Lebih dari dua | dua ritme utama + **wajib** memecah figuran dan melarang gerakan serempak |

Untuk satu tokoh:

```
MOVEMENT NOTE
Adit is still. He stands with his weight on one leg and his thumb on his phone, and he
does not shift, pace or look around. Every movement he makes is small and finished. He
never sits — when he goes down, he crouches.
```

Tanpa blok ini di scene ramai, AI video menggerakkan figuran serempak seperti paduan suara, dan
itu penanda paling cepat bahwa hasilnya dibuat AI.

```
MOVEMENT NOTE
Bu Dian and Rafa run on OPPOSITE rhythms. Bu Dian is fast and clipped, chin high, and plays
to the room — she turns toward the staff when she speaks. Rafa is slow and economical; he
never raises his voice, never gestures, and never looks at her for more than two seconds.
The twelve staff NEVER react as a block — one looks down, one looks away, one keeps
watching; never a synchronised crowd turn.
```

Dua hal yang dikerjakan blok ini:
1. Memberi tiap tokoh utama **ritme yang berbeda** — jangan sampai dua tokoh bergerak cermin.
2. **Memecah figuran** — sebut tiga reaksi berbeda, dan larang gerakan serempak secara eksplisit.

### 11 · SHOT BREAKDOWN

Judul bagiannya persis `SHOT BREAKDOWN`. Bukan `SCREENPLAY`, bukan `ACTION`, bukan `SCENE`.

```
SHOT BREAKDOWN

SCENE [00:00-00:30] RUANG RAPAT — one continuous confrontation, cut between positions:

SHOT 1 (0-4s), 85mm EXTREME CLOSE-UP, static, low: a man's hand lets a wrench down onto
the aluminium tray of a step-ladder. Off-screen, a woman's voice — cold, unhurried.

BU DIAN (off-screen): "Orang kayak kamu nggak akan pernah duduk di kursi ini."

SHOT 2 (4-10s), 35mm WIDE from the far end of the table, very slow push in: twelve staff
seated along the table, not one of them looking up. Beyond them BU DIAN stands with her arms
folded; behind her, high on a step-ladder, RAFA with the open air-conditioner panel above
his head. No dialogue — six seconds of dead room tone.

SHOT 3 (10-16s), 35mm MEDIUM from behind the seated staff at shoulder height, pushing slowly
toward BU DIAN: she turns a quarter away from him to address the room instead.

BU DIAN: "Tiga tahun saya di sini. Nggak pernah ada yang ngatur saya."

SHOT 4 (16-20s), 85mm CLOSE-UP, static, slightly low, on RAFA: half his face burnt white by
the window, the other half in deep shadow. He wipes his hands on a cloth. He does not answer.

SHOT 5 (20-26s), 85mm CLOSE-UP, static, on RAFA from the opposite side: he looks down at her
for the first time — flat, almost friendly.

RAFA: "Dian Puspitasari. Masuk dua ribu sebelas. Divisi personalia."

SHOT 6 (26-30s), 85mm CLOSE-UP on BU DIAN, extremely slow push: her arms come unfolded. She
says nothing. Behind her, one of the twelve finally lifts his head.

The shot ends on her face mid-realisation — no freeze frame, no fade to black.
```

Anatomi satu baris shot:

```
SHOT <n> (<mulai>-<selesai>s), <lensa> <UKURAN> from <posisi fisik>, <gerakan>: <aksi>.
```

Kalau satu generate memuat lebih dari satu referensi lokasi, tiap baris shot diberi **tag
lokasi** tepat setelah timecode — sisi mana, tempat mana, dilihat dari mana:

```
SHOT 6 (23-26s) — OUTSIDE, terrace, seen from the lane — 35mm MEDIUM, static, from out in
the lane, looking through the iron bars of the fence toward the house: ...

SHOT 7 (26-30s) — INSIDE, living-room floor, seen through the gap — 50mm, static, ...
```

Tag ditulis di **setiap** shot, termasuk yang lokasinya terasa jelas. Pengecek menolak prompt
berlokasi ganda yang satu shot-nya tanpa tag.

Aturan:
- Baris scene ditulis `SCENE [00:00-00:NN] LOKASI` — **tanpa nomor**. Tiap prompt adalah satu
  generate yang berdiri sendiri, jadi timecode-nya selalu mulai dari 00:00, termasuk untuk scene
  kedua dan ketiga sebuah episode. Nomor scene hanya ada di judul markdown di luar blok.
- `NN` sama dengan durasi di baris pertama `VIDEO STYLE & FORMAT`, dan selalu 4–30.
- Timecode shot ditulis `(0-4s)`. Harus bersambung tanpa celah dan tanpa tumpang tindih, dan shot
  terakhir berakhir tepat di `NN`.
- Dialog ditulis di baris terpisah, nama tokoh kapital, kalimatnya dalam tanda kutip, dalam bahasa
  yang dipilih user.
- Arahan intonasi dalam kurung setelah nama: `BU DIAN (off-screen)`, `RAFA (quietly)`.
- Shot tanpa dialog ditulis eksplisit: `No dialogue — six seconds of dead room tone.`
- Baris penutup selalu menjelaskan bagaimana klip berhenti, dan selalu **pada gerakan**:
  `no freeze frame, no fade to black`.
- **Shot lewat celah, kaca, jendela, atau dari mata tokoh: tulis hanya apa yang terlihat.**
  Jangan sebut nama tokoh, napasnya, matanya, atau kata tentang orang — termasuk daftar larangan
  seperti `no face, no head, nobody`. Kata-kata itu justru menanam wajah di frame. Larangan
  orang cukup sekali di CRITICAL. Kata `POV` juga tidak perlu; tulis letak lensanya.
- **Bekas atau ketiadaan benda ditulis sebagai permukaan**, bukan sebagai benda:
  `flat, level with the floor, nothing on it, not an object`. Jangan menegaskan kontrasnya
  dengan `darker` atau `deeper colour` — penegasan itu dirender jadi lempengan atau keset.
- **Sudut balik** (kamera menghadap ke arah datangnya tokoh) ditulis dengan letak kamera dan apa
  yang ada di belakang tokoh, sekali saja. Sudut yang tidak ada di plate tetap berisiko; lihat
  daftar shot berisiko di `konsep.md`.

## Yang dilarang masuk ke dalam blok prompt

| Dilarang | Alasan |
|---|---|
| Rasio — `9:16`, `vertical`, `horizontal` | diatur di pengaturan AI video sebelum generate |
| Resolusi, fps, seed, nama model | sama, itu pengaturan tool |
| Header manusia — `=== PROMPT VIDEO ... ===` | model tidak paham, bisa muncul sebagai teks di layar |
| Nama berkas — `rafa_sheet.png` | nama berkas ditulis di judul markdown di luar blok |
| Nomor episode, judul seri | tidak ada gunanya untuk model |
| `subtitle`, `caption` | kecuali di daftar larangan blok LANGUAGE |
| `8k`, `ultra realistic`, `masterpiece`, `award winning` | tidak membawa informasi, mengacaukan gaya |

## Saat menyerahkan ke user

Satu baris di atas daftar scene:

> Generate per scene. Lampirkan berkas yang disebut di tiap judul sebagai referensi gambar,
> lalu atur rasio dan durasi di pengaturan AI video sebelum generate.
