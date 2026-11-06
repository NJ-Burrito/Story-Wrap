# Prompt aset — <judul>

Generate aset ini dulu di AI gambar mana pun. Simpan dengan nama berkas yang tertulis di tiap
judul, karena nama itu yang dipakai sebagai token di `prompt-video.md`.

Pakai ulang dari ep <NN>, jangan generate ulang: `<berkas>`, `<berkas>`. <hapus baris ini di ep 01>

Aset baru di episode ini: <daftar>.

---

## Sheet karakter · <NAMA>
Simpan sebagai: `<nama>_sheet.png` → token `[gambar_<nama>]`

```
Character reference sheet for film production. Three panels side by side, separated by
thin subtle vertical gaps. One continuous neutral dark grey seamless studio backdrop
across all three panels. Soft even studio lighting, photorealistic cinematic photography,
35mm film look, fine grain, muted desaturated colour.

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

A clean white sans-serif label reading <NAMA> printed in the lower left corner of the
left panel.

The same person, the same face, the same clothing in all three panels. Photorealistic,
not illustration.

Avoid: more than one person per panel, different faces between panels, missing head,
patterned or gradient background, hard shadows, dramatic camera angles, extra text,
watermark, logo.
```

---

## Set plate · <NAMA LOKASI>
Simpan sebagai: `<nama>_plate.png` → token `[gambar_<nama>]`

```
Photorealistic interior photograph, absolutely no people in frame.

<blok set dari set.md, disalin apa adanya>

<waktu dan arah cahaya>. 24mm lens, eye height, level horizon, straight-on composition.

Avoid: people, text, signage, extra furniture, coloured practical lights, lens flare,
watermark.
```

---

## Plate properti · <NAMA PROPERTI>
Simpan sebagai: `<nama>_plate.png` → token `[gambar_<nama>]`

```
Photorealistic reference photograph of a single object, absolutely no people.

<blok properti dari set.md, disalin apa adanya>

Plain neutral grey seamless studio backdrop, soft even studio lighting. <sudut pandang yang
menampilkan ciri uniknya>, 35mm lens, eye height, the whole object in frame with space
around it.

Avoid: people, text, logos, brand names, extra accessories, watermark.
```
