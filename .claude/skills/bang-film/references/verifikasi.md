# Verifikasi & serah — gerbang 7

Tidak ada media yang bisa dilihat di gerbang ini. Yang diperiksa adalah teksnya, dan hampir semua
kesalahan di skill ini adalah kesalahan teks yang baru ketahuan setelah user membakar kredit.

## Langkah 1 · Jalankan pengecek

```
python assets/tools/check_prompts.py <folder proyek>
```

Python 3, tanpa dependensi. Di Windows, tambahkan `PYTHONIOENCODING=utf-8` kalau keluaran
terminal berantakan.

Yang dicek mesin:

| Cek | Rincian |
|---|---|
| Salinan identik | bentuk pendek cast di CHARACTERS, bentuk panjang + WARDROBE di sheet, blok set dan properti di LOCATION dan di plate |
| Sebelas blok | ada semua dan berurutan; `CONTINUITY`, kalau ada, di antara LOCATION dan AUDIO |
| Lokasi ganda | kalau satu prompt memakai lebih dari satu plate lokasi: tiap SHOT bertag lokasi, LOCATION memetakan plate ke shot, blok `CONTINUITY` ada |
| Durasi | tiap prompt 4–30 s; judul, baris pertama, dan baris SCENE sepakat; total episode = `brief.md`; scene di `naskah.md` 4–30 s |
| Timecode | SHOT bernomor urut, bersambung tanpa celah, berakhir tepat di durasi scene |
| Token & berkas | tiap token di prompt ada berkasnya di baris "Lampirkan"; tidak ada lampiran yang tokennya tak dipakai; nama berkas sejalan dengan token |
| Kata terlarang | rasio, `vertical`, `horizontal`, `===`, nama berkas, `SCREENPLAY`, resolusi, seed, fps, `8k`, `masterpiece`, dll; `subtitle`/`caption` di luar blok LANGUAGE |
| Frasa wajib | `Never two consecutive shots from the same position`, `NOT a montage`, `no freeze frame`, larangan subtitle, `exactly as written` atau `NO spoken dialogue` |
| Sheet | label nama, `missing head`, `different faces between panels`, urutan panel |
| Plate | `absolutely no people` |

Perbaiki sampai keluarannya `Semua cek lolos.` Jangan serahkan proyek yang belum lolos.

## Langkah 2 · Checklist yang tidak bisa dicek mesin

- [ ] Tidak ada dua shot berurutan dari posisi kamera yang sama — baca kolom posisi di shot list.
- [ ] `MOVEMENT NOTE` sesuai jumlah orang: satu tokoh membawa nada tubuh; lebih dari dua orang
      memecah figuran dan melarang gerakan serempak.
- [ ] Tidak ada beat penting yang bergantung pada tulisan yang harus dibaca.
- [ ] Hook, arc, set, dan alasan tokoh tidak bertentangan dengan premis.
- [ ] Rubrik `copywriting.md` sudah dijalankan; dua baris ya/tidak-nya bernilai ya.
- [ ] Pindaian klise sudah dijalankan.
- [ ] Genre yang bukan sudah disebut di VIDEO STYLE & FORMAT kalau premisnya bisa disalahbaca.
- [ ] Benda berlayar di frame sudah diberi `screen always angled away from camera`.
- [ ] Teks bebas di dalam shot tidak bertentangan dengan blok terkunci — misalnya menyebut ciri
      unik tokoh di sisi yang salah. Pengecek hanya memeriksa blok terkunci, bukan kalimat shot.
- [ ] Shot berisiko sudah dilaporkan di gerbang 4 dan keputusan user tercatat di `naskah.md`.
- [ ] Shot lewat celah, kaca, atau dari mata tokoh tidak menyebut tokoh atau kata tentang orang.
- [ ] Bekas atau ketiadaan benda ditulis sebagai permukaan rata, tanpa kata kontras.
- [ ] Tidak ada benda yang ditegaskan berulang-ulang di banyak blok.

## Kesalahan yang sering terjadi

| Gejala di hasil user | Penyebab di teks |
|---|---|
| Wajah berubah antar klip | deskripsi tokoh diparafrase di salah satu berkas, atau sheet salah lampir karena nama berkas tidak sejalan dengan token |
| Teks aneh muncul di layar | header manusia ikut ter-copy ke dalam prompt, atau larangan subtitle tidak ada di blok LANGUAGE |
| Huruf acak di label, plat nomor, layar HP | properti tidak diberi `no printed text` / `licence plate blank`, atau layar tidak diarahkan menjauhi kamera |
| Dialog keluar dalam bahasa Inggris | blok LANGUAGE tidak menyebut "speak the lines exactly as written" |
| Dialog diparafrase atau ditambah | sama, dan biasanya karena baris "do not invent extra lines" dihapus |
| Ada narasi atau gumaman di scene yang mestinya hening | blok LANGUAGE tidak memakai bentuk `NO spoken dialogue` |
| Figuran bergerak serempak | `MOVEMENT NOTE` tidak ada atau tidak melarang gerakan serempak secara eksplisit |
| Orang asing muncul di jalan yang mestinya sepi | CRITICAL tidak menulis `ONE character only. Nobody else appears at any point` |
| Drama keluarga terasa seperti film horor | VIDEO STYLE & FORMAT tidak menyebut `NOT horror` untuk premis yang bisa disalahbaca |
| Hasil terasa seperti montase | blok VIDEO STYLE & FORMAT tidak menegaskan "ONE continuous ... NOT a montage" |
| Potongan terasa monoton | dua shot berurutan dari posisi yang sama, atau aturan "never two consecutive shots" tidak ditulis |
| Frame terasa datar | LIGHTING ditulis dengan kata sifat, bukan sumber dan arah |
| Panel badan di sheet tanpa kepala | `missing head` tidak ada di daftar Avoid |
| Orang bertambah antar potongan | jumlah tokoh tidak disebut eksplisit di blok CRITICAL |
| Prompt ditolak tool atau klip terpotong | durasi di luar 4–30 detik per generate |
| Pintu atau ruangan berubah antar klip | jalan masuk tokoh tidak tertulis di blok set, jadi model mengarangnya |
| Tokoh tiba-tiba di sisi lain pintu, atau di dalam ruangan yang mestinya hanya diintip | dua plate lokasi tanpa peta referensi dan tag lokasi; pintu disebut tanpa menyebut sisinya |
| Wajah atau kepala muncul di shot lewat celah atau kaca | tokoh atau kata tentang orang disebut di shot itu — termasuk daftar larangan `no face, no head` |
| Kamera di sisi yang salah, kaca jadi bening, pintu terbuka | sudut yang tidak ada di plate; benda yang terus ditegaskan (`stays closed`) malah diubah model |
| Kendaraan atau benda hilang, dobel, atau pindah setelah potongan | tidak ada butir CONTINUITY yang menyebut tempat persisnya dan shot tempat ia terlihat |
| Shot wide menyalin komposisi plate, mengabaikan teks | plate dikomposisi dari sudut lain; sebagian model memperlakukan plate sebagai pandangan kamera |
| Bekas atau petak bersih jadi lempengan, keset, atau tambalan | ketiadaan ditegaskan dengan kata kontras (`darker`, `deeper colour`) alih-alih permukaan rata |
| Baris dialog tambahan di luar layar | close-up tanpa wajah di dekat momen dialog; teks tidak bisa mengunci ini sepenuhnya |

## Setelah user generate — memperbaiki prompt

User sering kembali membawa hasil video yang plot hole. Urutannya:

**1 · Bedah dulu, jangan menebak.** Kalau user mengirim berkasnya dan `ffmpeg` tersedia:

```
ffmpeg -i <video> -filter:v "select='gt(scene,0.25)',showinfo" -f null -
ffmpeg -i <video> -vf "fps=2,scale=240:-1,tile=7x5" kontak_%d.png
```

Yang pertama memberi titik potong untuk dicocokkan dengan timecode prompt. Yang kedua membuat
lembar kontak dua frame per detik. Kalau Whisper tersedia, transkrip juga dialognya — baris
tambahan sering tidak terlihat di gambar. Cek dulu bahwa videonya benar: model, versi prompt,
dan rasionya.

**2 · Pisahkan plot hole dari penyimpangan.** Shot yang diambil dari sudut lain tapi ceritanya
tetap utuh bukan masalah. Pintu yang terbuka di cerita tentang rumah yang tidak pernah membuka
pintu adalah masalah.

**3 · Perbaiki dengan satu atau dua kalimat yang menyasar penyebab.** Pakai tabel gejala di atas.
Simpan sebagai versi baru — `prompt-video-v2.md`, `-v3.md` — jangan menimpa yang lama.

**4 · Uji dengan syarat yang sama:** model, rasio, dan gambar referensi yang sama dengan hasil
yang dibandingkan. Rasio yang berubah bisa ikut mengubah hasil, jadi perbandingannya tidak adil.

**5 · Kalau versi baru lebih buruk, kembali ke versi sebelumnya.** Jangan menumpuk perbaikan.
Prompt yang makin panjang tidak membuat model makin patuh. Setiap benda dan penegasan baru adalah
hal baru yang bisa diubah model. Satu uji pernah memburuk dari tiga plot hole menjadi empat
setelah tambahan penegasan.

**6 · Plot hole yang bertahan dua putaran adalah batas model, bukan batas teks.** Tawarkan
mengganti shot-nya dengan alternatif dari tabel shot berisiko, atau model lain. Kalau model lain
bersih dengan prompt yang sama, masalahnya ada di model.

Versi yang dipilih user disalin menjadi `prompt-video.md`. Pengecek hanya membaca nama itu.

## Bentuk serah

Daftar berkas, lalu cara pakai. Jangan menyebut model AI tertentu — user bebas memilih.

```markdown
Selesai, dan pengecek lolos. Berkasnya:

film/<judul>/
├── brief.md
├── konsep.md
├── cast.md
├── set.md
└── ep01/
    ├── naskah.md
    ├── prompt-aset.md
    └── prompt-video.md

Urutan pakainya:
1. Generate semua aset di `prompt-aset.md`, simpan dengan nama berkas yang tertulis di tiap judul.
2. Buka `prompt-video.md`, generate per scene. Lampirkan berkas yang disebut di judul scene itu.
3. Atur rasio dan durasi di pengaturan AI video sebelum generate — durasinya tertulis di judul.
4. Sambung scene berurutan di editor.
```

Sebutkan juga kelemahan yang kamu tahu masih ada — misalnya satu scene yang shot-nya terasa
sedikit, atau satu tokoh yang ciri uniknya kurang kuat. Lebih baik user tahu sebelum generate.
