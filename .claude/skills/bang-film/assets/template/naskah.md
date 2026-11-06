# Naskah — Ep <NN> · <judul episode>

## Dialog

Dibaca sebagai cerita. Baris tanpa dialog tetap diberi nomor shot — diam adalah beat.

**s01** · <NAMA> *(arahan intonasi)*
"<kalimat>"

**s02** · <NAMA> — <aksi tanpa dialog>

## Shot list

| Shot | Durasi | Set | Siapa | Ukuran | Posisi kamera | Dialog |
|---|---|---|---|---|---|---|
| s01 | <n> s | | | | | |

Total: <n> detik — target `brief.md`: <n> detik.

## Shot berisiko

Faktor dari tabel shot berisiko di `references/konsep.md`. Dilaporkan ke user bersama shot list;
user yang memutuskan. Tulis "Tidak ada" kalau memang tidak ada.

| Shot | Faktor | Keputusan user |
|---|---|---|
| s<nn> | <faktor> | <dipertahankan / diganti dengan ...> |

## Pembagian scene

Satu scene = satu prompt video = satu kali generate = **4–30 detik**. Pindah lokasi selalu scene
baru; di satu lokasi yang lebih dari 30 detik, pecah di jeda alami, tidak di tengah dialog.

| Scene | Shot | Durasi | Lokasi |
|---|---|---|---|
| 1 | s01–s0<n> | <n> s | <lokasi> |
