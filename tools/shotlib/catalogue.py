"""Catalogue lookup (stage catalogue). A ref is 'id@version' (e.g. hero/pose/write-card@3.0); the index is
catalogue/characters/<character>/index.json. Look up before build (R-346); versions are immutable (R-347).
Failure ids: CATALOGUE-MISSING (a ref or file the shot uses is not in the catalogue and not declared new),
CATALOGUE-FILE (an index entry points at a file that is not on disk)."""
from __future__ import annotations
import json
from pathlib import Path


def vkey(v: str):
    return tuple(int(x) if x.isdigit() else 0 for x in str(v).split("."))


class Catalogue:
    def __init__(self, root: Path, character: str):
        self.root = Path(root)
        self.dir = self.root / "catalogue" / "characters" / character
        self.index_path = self.dir / "index.json"
        self.entries = json.loads(self.index_path.read_text(encoding="utf-8"))["entries"] if self.index_path.is_file() else []
        self.by_ref = {f"{e['id']}@{e['version']}": e for e in self.entries}

    def has(self, ref: str) -> bool:
        return ref in self.by_ref

    def latest(self, id_: str):
        vs = [e["version"] for e in self.entries if e["id"] == id_]
        return max(vs, key=vkey) if vs else None

    def camera_ref(self, character: str, name: str) -> str:
        """Newest catalogue version of hero/camera/<name> ('ms-eye-flat' -> 'hero/camera/ms-eye-flat@2.0')."""
        id_ = f"{character}/camera/{name}"
        v = self.latest(id_)
        return f"{id_}@{v}" if v else f"{id_}@MISSING"

    def file_of(self, ref: str):
        e = self.by_ref.get(ref)
        return self.dir / e["path"] if e else None


def actor_list(shot: dict) -> list[dict]:
    """The actors of a shot: shot.json `actors` (several characters, tools/render/characters/README.md) or the one `character` of a v5-style shot."""
    if shot.get("actors"):
        return shot["actors"]
    return [{"id": shot["character"], "module": shot["character"], "uses": shot.get("uses", {}), "catalogue": shot["catalogue"]}]


def used_refs(shot: dict, actor: dict | None = None) -> dict:
    """Everything shot.json says an actor uses: refs (id@ver) and plain files under the character folder (optional keys: writing, props)."""
    a = actor or actor_list(shot)[0]
    refs = list((a.get("uses") or {}).get("refs", []))
    ck = a["catalogue"]
    files = [ck[k] for k in ("model", "face", "hand_model", "writing") if ck.get(k)]
    files += [v for v in (ck.get("props") or {}).values()]
    files += [ck["grip_dir"] + g + ".json" for g in ck.get("grips", [])]
    files += [ck["expression_dir"] + e + ".json" for e in ck.get("expressions", [])]
    return {"refs": refs, "files": files}


def check(shot: dict, root: Path, extra_refs=()) -> tuple[dict, list[str]]:
    """Return (report, failures). The report lists found refs and what must be built new; every actor is looked up in its own character catalogue."""
    declared_new = set(shot.get("new", []))
    found, missing, to_build, fails, files_missing = [], [], [], [], []
    for n, a in enumerate(actor_list(shot)):
        cat = Catalogue(root, a["module"])
        used = used_refs(shot, a)
        for ref in list(used["refs"]) + (list(extra_refs) if n == 0 else []):
            if cat.has(ref):
                found.append(ref)
            elif ref in declared_new:
                to_build.append(ref)
            else:
                missing.append(ref)
                fails.append(f"CATALOGUE-MISSING {ref} is not in the {a['module']} catalogue and not declared in shot.json 'new'")
        for r in declared_new:
            if r.split("/")[0] == a["module"] and r not in to_build and not cat.has(r) and r not in missing:
                to_build.append(r)
        if not cat.index_path.is_file():
            fails.append(f"CATALOGUE-MISSING no index at {cat.index_path}")
        for f in used["files"]:
            if not (cat.dir / f).is_file():
                files_missing.append(f"{a['module']}/{f}")
                fails.append(f"CATALOGUE-MISSING file {cat.dir / f} does not exist")
        for e in cat.entries:
            if not (cat.dir / e["path"]).is_file() and f"{e['id']}@{e['version']}" in set(used["refs"]):
                fails.append(f"CATALOGUE-FILE index entry file {e['path']} is not on disk")
    report = {"character": shot.get("character") or [a["id"] for a in actor_list(shot)], "actors": [a["id"] for a in actor_list(shot)], "found": sorted(set(found)), "missing": sorted(set(missing)),
              "files_missing": files_missing, "to_build": sorted(set(to_build)),
              "note": "to_build entries need a build-up sheet and a catalogue entry before the spec gate accepts them (POSE-CATALOGUE)"}
    return report, fails


def input_files(shot: dict, root: Path) -> list[Path]:
    """Every file whose content a shot's output depends on, so a stage that lists them reruns when one changes: per actor the index, the plain
    files (model, face, hand model, writing, props, grips, expressions), every file behind a ref in uses.refs, the character module JS, plus the
    world module JS and the world's catalogue JSON (catalogue/environments/<world>/, sheet images skipped). Missing files are skipped (the
    catalogue stage reports them). Sorted, de-duplicated."""
    root = Path(root)
    out: set[Path] = set()
    try:
        actors = actor_list(shot)
    except KeyError:
        actors = []
    for a in actors:
        cat = Catalogue(root, a["module"])
        out.add(cat.index_path)
        out.add(root / "tools" / "render" / "characters" / f"{a['module']}.js")
        used = used_refs(shot, a)
        out.update(cat.dir / f for f in used["files"])
        for ref in used["refs"]:
            f = cat.file_of(ref)
            if f is not None:
                out.add(f)
    world = shot.get("world")
    if world:
        out.add(root / "tools" / "render" / "worlds" / f"{world}.js")
        env = root / "catalogue" / "environments" / world
        if env.is_dir():
            out.update(q for q in env.rglob("*.json") if q.is_file() and "sheets" not in q.relative_to(env).parts)
    return sorted(p for p in out if p.is_file())
