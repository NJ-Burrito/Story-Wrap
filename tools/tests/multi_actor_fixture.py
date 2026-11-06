"""Builder of the two-actor pass fixture: a spec (from kb/quality/shot-spec.example.json, one character made two) and a rig trace
(from test_rig_checks.make_trace, one character made two, plus the scene block). `python tools/tests/multi_actor_fixture.py` writes them to
kb/quality/fixtures/two-actor.shot-spec.json and two-actor.rig-trace.json; tests/test_multi_actor.py asserts the stored files equal what this builds.
The fail fixtures are one-line mutations of these (test_multi_actor.py), so each new check id has a passing and a failing case."""
import copy, json, sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS)); sys.path.insert(0, str(TOOLS / "tests"))

FPS, N = 24, 144
HANDOFF = 90                      # frame of the hand-off (3.75 s), inside b2 (3..6 s = frames 72..144)


def two_spec() -> dict:
    sp = json.loads((REPO / "kb/quality/shot-spec.example.json").read_text(encoding="utf-8"))
    hero = sp["characters"][0]
    partner = copy.deepcopy(hero); partner["id"] = "partner"
    sp["characters"] = [hero, partner]
    sp["actors"] = [{"id": "hero", "module": "hero", "depth_z": 2.4, "layer": 0, "catalogue_refs": ["hero/model@1.0"]},
                    {"id": "partner", "module": "partner", "depth_z": 2.8, "layer": 1, "catalogue_refs": ["partner/model@1.0"]}]
    sp["props"] = list(sp.get("props", [])) + [{"id": "cup", "physics_profile": "rigid", "mass_class": "light"}]
    sp.setdefault("physics_profiles", {}).setdefault("rigid", {"kind": "object", "material": "rigid", "mass_class": "light", "stretch": {"max_scale": 1.0}})
    for b in sp["beats"]:
        em, tk = b["emotion"], b["emotion_track"]
        b["actor_emotions"] = {"hero": {"emotion": copy.deepcopy(em), "emotion_track": copy.deepcopy(tk)},
                               "partner": {"emotion": copy.deepcopy(em), "emotion_track": copy.deepcopy(tk)}}
        p2 = copy.deepcopy(b["poses"][0]); p2["character"] = "partner"; b["poses"].append(p2)
        b["cast_shadows"].append({"caster": "partner", "receiver": "back-unit", "source": "mass_proxy", "proxy": "partner-proxy", "light": "key", "self_shadow": True, "edge": "hard"})
        b["draw_order"] = [{"order": ["partner", "hero"]}]   # partner is farther (depth_z 2.8): drawn first
    sp["actor_interactions"] = [
        {"id": "shake", "kind": "contact", "beat": "b1", "t0": 1.0, "t1": 2.0, "why": "the two shake hands in greeting",
         "a": {"actor": "hero", "point": "hand_R"}, "b": {"actor": "partner", "point": "hand_L"}, "tol_px": 8},
        {"id": "touch-cup", "kind": "contact", "beat": "b2", "t0": 3.0, "t1": 3.75, "why": "the partner's fingers meet the cup the hero still holds",
         "a": {"actor": "partner", "point": "hand_L"}, "b": {"prop": "cup", "held_by": {"actor": "hero", "hand": "R"}}, "tol_px": 8},
        {"id": "pass-cup", "kind": "handover", "beat": "b2", "t0": 3.0, "t1": 4.5, "why": "the hero hands the cup over",
         "prop": "cup", "giver": {"actor": "hero", "hand": "R"}, "receiver": {"actor": "partner", "hand": "L"}, "handoff_frame": HANDOFF, "both_hands_frames": 3},
    ]
    sp["beats"][0]["actor_emotions"]["partner"]["emotion"]["peak_s"] = sp["beats"][0]["emotion"]["peak_s"]
    return sp


def cup_pos(f: int):
    return [600.0 + 0.5 * f, 500.0]


def two_trace() -> dict:
    from test_rig_checks import make_trace
    base = make_trace()
    tr = {"fps": FPS, "canvas": {"w": 1080, "h": 1920}, "characters": {}, "scene": {"actors": [{"id": "hero", "module": "hero", "z": 2.4, "layer": 0}, {"id": "partner", "module": "partner", "z": 2.8, "layer": 1}], "frames": []}}
    for cid in ("hero", "partner"):
        ch = copy.deepcopy(base["characters"]["hero"]); tr["characters"][cid] = ch
    far = [100.0, 900.0]
    for i in range(N):
        pos = cup_pos(i)
        hero_hand = pos if 72 <= i <= HANDOFF + 18 else ([600.0, 500.0] if 24 <= i < 48 else far)
        partner_hand = ([hero_hand[0] + 3.0, hero_hand[1] + 2.0] if 24 <= i < 48 else (pos if 72 <= i <= HANDOFF + 18 else [400.0, 900.0]))
        if 72 <= i < 90:   # partner's fingers close on the cup the hero holds
            partner_hand = [pos[0] + 2.0, pos[1]]
        tr["characters"]["hero"]["frames"][i]["contact_points"]["hand_R"] = hero_hand
        tr["characters"]["partner"]["frames"][i]["contact_points"]["hand_L"] = partner_hand
        giver_holds = i < HANDOFF
        hands = []
        if HANDOFF - 3 <= i < HANDOFF:
            hands = [{"actor": "hero", "hand": "R", "gap_px": 2.0}, {"actor": "partner", "hand": "L", "gap_px": 3.0}]
        elif giver_holds:
            hands = [{"actor": "hero", "hand": "R", "gap_px": 2.0}]
        else:
            hands = [{"actor": "partner", "hand": "L", "gap_px": 2.0}]
        tr["scene"]["frames"].append({
            "f": i, "t": i / FPS, "present": ["hero", "partner"], "draw_order": ["partner:body", "partner:arms", "hero:body", "hero:arms"],
            "depth": {"hero": 2.4, "partner": 2.8},
            "props": [{"id": "cup", "pos": pos, "parent": {"actor": "hero", "hand": "R"} if giver_holds else {"actor": "partner", "hand": "L"}, "hands": hands, "touch": [pos]}]})
    return tr


if __name__ == "__main__":
    d = REPO / "kb/quality/fixtures"
    (d / "two-actor.shot-spec.json").write_text(json.dumps(two_spec(), ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "two-actor.rig-trace.json").write_text(json.dumps(two_trace(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("wrote", d)
