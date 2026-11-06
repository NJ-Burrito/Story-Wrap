#!/usr/bin/env python3
"""Cek keluaran proyek bang-film sebelum diserahkan ke user (gerbang 7).

Pakai:  python check_prompts.py <folder proyek>
Contoh: python check_prompts.py film/alamat-yang-sama

Yang dicek:
- blok cast, set, dan properti tersalin identik dari cast.md / set.md
- sebelas blok prompt video lengkap dan berurutan, CONTINUITY (opsional) di tempatnya
- prompt dengan lebih dari satu plate lokasi: tag lokasi di tiap SHOT, peta referensi di
  LOCATION, blok CONTINUITY ada
- timecode SHOT bersambung tanpa celah dan berakhir tepat di durasi scene
- durasi tiap prompt video 4-30 detik (satu kali generate)
- total durasi per episode sama dengan brief.md
- token [gambar_x] cocok dengan berkas di baris "Lampirkan" dan "Simpan sebagai"
- kata terlarang di dalam blok prompt (rasio, header, nama berkas, kata kosong)

Yang tidak dicek dan tetap harus dilihat manusia: dua shot berurutan dari posisi kamera
yang sama, mutu naskah, dan apakah MOVEMENT NOTE benar-benar memecah figuran.
"""
import pathlib
import re
import sys

BLOK = ["VIDEO STYLE & FORMAT", "LANGUAGE", "OPTICS", "CAMERA", "LIGHTING", "CRITICAL",
        "CHARACTERS", "LOCATION", "AUDIO", "MOVEMENT NOTE", "SHOT BREAKDOWN"]
OPSIONAL = {"CONTINUITY": "LOCATION"}  # blok opsional -> blok yang tepat mendahuluinya
TERLARANG = ["9:16", "16:9", "4:5", "21:9", "vertical", "horizontal", "===", ".png", ".jpg",
             "SCREENPLAY", "resolution", "seed", "fps", "8k", "4k", "masterpiece",
             "award winning", "ultra realistic", "hyper detailed"]
DURASI_MIN, DURASI_MAKS = 4, 30
TOKEN = r"\[(gambar_[a-z0-9_]+)\]"

masalah = []
jumlah = {"prompt video": 0, "prompt aset": 0, "naskah": 0}


def lapor(tempat, pesan):
    masalah.append(f"{tempat}: {pesan}")


def rata(teks):
    return " ".join(teks.split())


def blok_kode(teks):
    return re.findall(r"```[^\n]*\n(.*?)```", teks, re.S)


def baca_cast(folder):
    cast = {}
    for sek in re.split(r"\n#{2,3} ", (folder / "cast.md").read_text(encoding="utf-8"))[1:]:
        kode = blok_kode(sek)
        token = re.search(r"Token: `" + TOKEN + "`", sek)
        if len(kode) < 2 or not token:
            continue
        berkas = re.search(r"Berkas sheet: `([^`]+)`", sek)
        cast[token.group(1)] = {"nama": sek.splitlines()[0].strip(),
                                "berkas": berkas.group(1) if berkas else None,
                                "panjang": kode[0], "pendek": kode[1]}
    return cast


def baca_set(folder):
    # Lokasi ditulis sebagai "## NAMA", properti sebagai "### NAMA" di bawah "## Properti".
    sets = {}
    bagian = re.split(r"\n(#{2,3}) ", (folder / "set.md").read_text(encoding="utf-8"))
    for pagar, sek in zip(bagian[1::2], bagian[2::2]):
        kode = blok_kode(sek)
        if not kode:
            continue
        token = re.search(r"Token: `" + TOKEN + "`", sek)
        berkas = re.search(r"Berkas plate: `([^`]+)`", sek)
        sets[sek.splitlines()[0].strip()] = {"token": token.group(1) if token else None,
                                             "berkas": berkas.group(1) if berkas else None,
                                             "blok": kode[0], "properti": pagar == "###"}
    return sets


def cek_nama_berkas(tempat, token, berkas):
    if berkas and not berkas.startswith(token[len("gambar_"):] + "_"):
        lapor(tempat, f"nama berkas {berkas} tidak sejalan dengan token [{token}]")


def pecah_blok(tempat, blk):
    posisi = {}
    for b in BLOK + list(OPSIONAL):
        m = re.search(r"^" + re.escape(b) + r"\b", blk, re.M)
        if m:
            posisi[b] = m.start()
        elif b in BLOK:
            lapor(tempat, f"blok {b} tidak ada")
    ada = [posisi[b] for b in BLOK if b in posisi]
    if ada != sorted(ada):
        lapor(tempat, "urutan sebelas blok salah")
    for b, sebelum in OPSIONAL.items():
        if b in posisi:
            sesudah = BLOK[BLOK.index(sebelum) + 1]
            if not posisi.get(sebelum, -1) < posisi[b] < posisi.get(sesudah, -1):
                lapor(tempat, f"blok {b} harus di antara {sebelum} dan {sesudah}")
    awal = sorted(posisi.values())
    isi = {}
    for b, p in posisi.items():
        berikut = [q for q in awal if q > p]
        isi[b] = blk[p:min(berikut) if berikut else len(blk)]
    return isi


def cek_durasi(tempat, blk, dur_judul):
    m = re.search(r"^(\d+)-second scene", blk, re.M)
    dur = int(m.group(1)) if m else None
    if dur is None:
        lapor(tempat, "durasi tidak disebut di awal VIDEO STYLE & FORMAT")
        return 0
    if not DURASI_MIN <= dur <= DURASI_MAKS:
        lapor(tempat, f"durasi {dur} s di luar {DURASI_MIN}-{DURASI_MAKS} detik per generate")
    if dur_judul is not None and dur_judul != dur:
        lapor(tempat, f"judul bilang {dur_judul} detik, prompt bilang {dur} detik")
    m = re.search(r"^SCENE \[00:00-00:(\d\d)\]", blk, re.M)
    if not m:
        lapor(tempat, "baris SCENE [00:00-00:NN] tidak ada")
    elif int(m.group(1)) != dur:
        lapor(tempat, f"timecode SCENE berakhir di {m.group(1)} s, durasi {dur} s")
    if re.search(r"^SCENE \d", blk, re.M):
        lapor(tempat, "SCENE bernomor di dalam prompt — tiap prompt satu generate, tanpa nomor")
    shots = re.findall(r"^SHOT (\d+) \((\d+)-(\d+)s\)", blk, re.M)
    if not shots:
        lapor(tempat, "tidak ada baris SHOT")
        return dur
    harap = 0
    for i, (n, a, b) in enumerate(shots, 1):
        if int(n) != i:
            lapor(tempat, f"SHOT {n} seharusnya bernomor {i}")
        if int(a) != harap:
            lapor(tempat, f"SHOT {n} mulai di {a} s, seharusnya {harap} s")
        if int(b) <= int(a):
            lapor(tempat, f"SHOT {n} berdurasi nol atau mundur")
        harap = int(b)
    if harap != dur:
        lapor(tempat, f"SHOT terakhir berakhir di {harap} s, durasi scene {dur} s")
    return dur


def cek_prompt_video(f, cast, sets):
    total = 0
    peta = {t: c["berkas"] for t, c in cast.items()}
    peta.update({s["token"]: s["berkas"] for s in sets.values() if s["token"]})
    for sek in re.split(r"\n## ", f.read_text(encoding="utf-8"))[1:]:
        kode = blok_kode(sek)
        if not kode:
            continue
        judul = sek.splitlines()[0].strip()
        tempat = f"{f.parent.name}/{f.name} [{judul}]"
        blk = kode[0]
        blk_rata = rata(blk)
        jumlah["prompt video"] += 1

        isi = pecah_blok(tempat, blk)

        for kata in TERLARANG:
            if kata.lower() in blk_rata.lower():
                lapor(tempat, f"kata terlarang di dalam prompt: {kata!r}")
        luar_language = blk_rata.lower().replace(rata(isi.get("LANGUAGE", "")).lower(), "")
        for kata in ("subtitle", "caption"):
            if kata in luar_language:
                lapor(tempat, f"'{kata}' muncul di luar blok LANGUAGE")

        m = re.search(r"(\d+) detik", judul)
        total += cek_durasi(tempat, blk, int(m.group(1)) if m else None)

        baris = next((l for l in sek.splitlines() if l.startswith("Lampirkan:")), "")
        lampiran = set(re.findall(r"`([^`]+)`", baris))
        dipakai = set(re.findall(TOKEN, blk))
        for t in sorted(dipakai):
            if t not in peta:
                lapor(tempat, f"token [{t}] tidak terdaftar di cast.md / set.md")
            elif peta[t] not in lampiran:
                lapor(tempat, f"token [{t}] dipakai tapi {peta[t]} tidak ada di baris Lampirkan")
        for b in sorted(lampiran - {peta.get(t) for t in dipakai}):
            lapor(tempat, f"{b} dilampirkan tapi tokennya tidak dipakai di prompt")

        char = rata(isi.get("CHARACTERS", ""))
        for t, c in cast.items():
            if t in dipakai and rata(c["pendek"].split("<")[0]) not in char:
                lapor(tempat, f"bentuk pendek {c['nama']} tidak identik dengan cast.md")
        lok = rata(isi.get("LOCATION", ""))
        for nama, s in sets.items():
            b = rata(s["blok"])
            if s["token"]:
                if s["token"] in dipakai and b not in lok:
                    lapor(tempat, f"blok {nama} tidak identik dengan set.md")
            elif b[:40] in blk_rata and b not in lok:
                lapor(tempat, f"properti {nama} dipakai tapi tidak tersalin identik di LOCATION")

        lokasi = [s for s in sets.values() if s["token"] in dipakai and not s["properti"]]
        if len(lokasi) > 1:
            ganda = f"{len(lokasi)} plate lokasi dalam satu generate"
            for n in re.findall(r"^SHOT (\d+) \(\d+-\d+s\)(?! — [^—]{1,80} —)", blk, re.M):
                lapor(tempat, f"SHOT {n} tanpa tag lokasi ({ganda})")
            if "SHOT" not in lok:
                lapor(tempat, f"LOCATION tidak memetakan plate ke shot ({ganda})")
            if "CONTINUITY" not in isi:
                lapor(tempat, f"blok CONTINUITY tidak ada untuk mengunci posisi tokoh ({ganda})")

        if "Never two consecutive shots from the same position" not in rata(isi.get("CAMERA", "")):
            lapor(tempat, "CAMERA tidak memuat 'Never two consecutive shots from the same position'")
        lang = rata(isi.get("LANGUAGE", ""))
        if "No subtitles" not in lang:
            lapor(tempat, "LANGUAGE tidak melarang subtitle")
        if "exactly as written" not in lang and "NO spoken dialogue" not in lang:
            lapor(tempat, "LANGUAGE tidak memuat 'exactly as written' atau 'NO spoken dialogue'")
        if "NOT a montage" not in blk_rata:
            lapor(tempat, "VIDEO STYLE & FORMAT tidak memuat 'NOT a montage'")
        if "no freeze frame" not in blk_rata:
            lapor(tempat, "penutup tidak memuat 'no freeze frame'")
    return total


def cek_prompt_aset(f, cast, sets):
    for sek in re.split(r"\n## ", f.read_text(encoding="utf-8"))[1:]:
        kode = blok_kode(sek)
        if not kode:
            continue
        tempat = f"{f.parent.name}/{f.name} [{sek.splitlines()[0].strip()}]"
        blk = rata(kode[0])
        jumlah["prompt aset"] += 1
        simpan = re.search(r"Simpan sebagai: `([^`]+)` → token `" + TOKEN + "`", sek)
        if not simpan:
            lapor(tempat, "baris 'Simpan sebagai: `berkas` → token `[gambar_x]`' tidak ada")
            continue
        berkas, token = simpan.groups()
        cek_nama_berkas(tempat, token, berkas)
        if token in cast:
            c = cast[token]
            if c["berkas"] != berkas:
                lapor(tempat, f"berkas {berkas} beda dengan cast.md ({c['berkas']})")
            orang, _, baju = c["panjang"].partition("WARDROBE:")
            if rata(orang) not in blk:
                lapor(tempat, f"bentuk panjang {c['nama']} tidak identik dengan cast.md")
            if rata("WARDROBE:" + baju) not in blk:
                lapor(tempat, f"WARDROBE {c['nama']} tidak identik dengan cast.md")
            if f"label reading {c['nama']}" not in blk:
                lapor(tempat, f"label nama {c['nama']} tidak ada")
            for wajib in ("missing head", "different faces between panels"):
                if wajib not in blk:
                    lapor(tempat, f"Avoid tidak memuat '{wajib}'")
            urut = [blk.find(p) for p in ("LEFT PANEL: tight close-up", "MIDDLE PANEL", "RIGHT PANEL")]
            if -1 in urut or urut != sorted(urut):
                lapor(tempat, "panel harus berurutan: close-up kiri, depan tengah, belakang kanan")
        else:
            s = next((s for s in sets.values() if s["token"] == token), None)
            if not s:
                lapor(tempat, f"token [{token}] tidak terdaftar di cast.md / set.md")
                continue
            if s["berkas"] != berkas:
                lapor(tempat, f"berkas {berkas} beda dengan set.md ({s['berkas']})")
            if rata(s["blok"]) not in blk:
                lapor(tempat, "blok tidak identik dengan set.md")
            if "absolutely no people" not in blk:
                lapor(tempat, "plate tidak memuat 'absolutely no people'")


def cek_naskah(f, durasi_ep):
    teks = f.read_text(encoding="utf-8")
    tempat = f"{f.parent.name}/{f.name}"
    jumlah["naskah"] += 1
    total = sum(int(d) for d in re.findall(r"^\| s\d+ \| (\d+) s \|", teks, re.M))
    if durasi_ep and total != durasi_ep:
        lapor(tempat, f"shot list berjumlah {total} s, brief {durasi_ep} s")
    for d in re.findall(r"^\| \d+ \| s\d+[^|]*\| (\d+) s \|", teks, re.M):
        if not DURASI_MIN <= int(d) <= DURASI_MAKS:
            lapor(tempat, f"scene {d} s di luar {DURASI_MIN}-{DURASI_MAKS} detik per generate")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    folder = pathlib.Path(sys.argv[1])
    m = re.search(r"\| Durasi \| (\d+) detik", (folder / "brief.md").read_text(encoding="utf-8"))
    durasi_ep = int(m.group(1)) if m else None
    cast, sets = baca_cast(folder), baca_set(folder)
    for t, c in cast.items():
        cek_nama_berkas("cast.md", t, c["berkas"])
    for s in sets.values():
        if s["token"]:
            cek_nama_berkas("set.md", s["token"], s["berkas"])

    for ep in sorted(p for p in folder.iterdir() if p.is_dir() and p.name.startswith("ep")):
        if (ep / "naskah.md").exists():
            cek_naskah(ep / "naskah.md", durasi_ep)
        if (ep / "prompt-aset.md").exists():
            cek_prompt_aset(ep / "prompt-aset.md", cast, sets)
        if (ep / "prompt-video.md").exists():
            total = cek_prompt_video(ep / "prompt-video.md", cast, sets)
            if durasi_ep and total != durasi_ep:
                lapor(f"{ep.name}/prompt-video.md", f"total {total} s, brief {durasi_ep} s")
        else:
            lapor(ep.name, "prompt-video.md belum ada")

    print(f"Dicek: {len(cast)} tokoh, {len(sets)} set & properti, {jumlah['naskah']} naskah, "
          f"{jumlah['prompt aset']} prompt aset, {jumlah['prompt video']} prompt video.")
    if masalah:
        print(f"\n{len(masalah)} masalah:")
        for p in masalah:
            print(f"  - {p}")
        sys.exit(1)
    print("Semua cek lolos.")


if __name__ == "__main__":
    main()
