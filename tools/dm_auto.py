# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Automatic DM features for the Story-Wrap pages, the kind big creator profiles have (owner, 2026-10-27). Official Meta Messaging APIs only; texts live in
data/engage/dm_auto.json; tools/engage.py calls the helpers here on every tick.

    uv run tools/dm_auto.py status                  the config, the live ice breakers (read only) and the gate check of every text
    uv run tools/dm_auto.py apply [--go]            set the Instagram ice breakers (FAQ buttons shown when someone opens a DM); dry unless --go

Features
  (a) Ice Breakers: up to 4 question buttons (<= 80 characters) set with POST /{page-id}/messenger_profile (platform=instagram). A tap arrives as a message whose
      text is the question; the tick matches it (match_ice) and sends the canned answer.
  (b) Welcome: the first DM from a person that is only a greeting or a short remark gets the welcome text once (welcome_for).
  (c) Comment-to-DM: a comment with a keyword gets ONE private reply (POST /{page-id}/messages, recipient.comment_id; within 7 days of the comment, one per comment),
      at most once per person per post (keyword_hit, private_reply).
  (d) Reactions: a love reaction on the viewer's DM (sender_action react, Instagram and Messenger).
API shapes are written from Meta's documented Instagram Messaging API (Ice Breakers, Private Replies, sender actions); the doc pages need JavaScript, so they were
NOT re-read in this build: the first --go is the check, and any error is reported, never worked around.
Never: DM someone who did not write first (except the private reply to their own comment), send a link, follow or add anyone, write tashkeel.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import ig   # noqa: E402

CONFIG_REL = Path("data") / "engage" / "dm_auto.json"
ICE_MAX, ICE_Q_MAX = 4, 80
PM_WINDOW_DAYS = 7
REACTION = "love"


def config_path(root: Path | None = None) -> Path:
    p = Path(root or ig.REPO) / CONFIG_REL
    return p if p.is_file() else TOOLS.parent / CONFIG_REL


def load_config(root: Path | None = None) -> dict:
    try:
        c = json.loads(config_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    c.setdefault("ice_breakers", [])
    c.setdefault("welcome", {})
    c.setdefault("comment_to_dm", {})
    return c


def _n(s) -> str:
    import engage
    return engage.norm_ar(s).strip(" ؟?!.،")


def match_ice(text: str, cfg: dict) -> str | None:
    """The canned answer when the message is exactly one of the ice-breaker questions (a tap sends the question as text), else None."""
    t = _n(text)
    if not t:
        return None
    for b in cfg.get("ice_breakers", []):
        if _n(b.get("question")) == t:
            return b.get("answer") or None
    return None


def welcome_for(cfg: dict) -> str | None:
    return (cfg.get("welcome") or {}).get("text") or None


def keyword_hit(text: str, cfg: dict) -> str | None:
    """The private-reply text when the comment contains one of the keywords, else None."""
    c = cfg.get("comment_to_dm") or {}
    n = _n(text)
    if not c.get("text") or not n:
        return None
    for k in c.get("keywords", []):
        if _n(k) and _n(k) in n:
            return c["text"]
    return None


def strip_keywords(text: str, cfg: dict) -> str:
    """The text without the trigger words, so the spam/sensitive classifier judges what is left (a bare «رابط» is not spam here, a phone number still is)."""
    import re
    t = _n(text)
    for k in (cfg.get("comment_to_dm") or {}).get("keywords", []):
        if _n(k):
            t = re.sub(re.escape(_n(k)), " ", t)
    return t


# ------------------------------------------------------------------ API calls (official Messaging API; replaced in tests)
def _penv(env: dict) -> dict:
    penv = ig.publish_env(env)
    ig.need(penv, "FB_PAGE_ID", "IG_ACCESS_TOKEN")
    return penv


def private_reply(env: dict, comment_id: str, text: str) -> str:
    """ONE private reply DM to the author of a comment (Instagram Private Replies; the same call with a Page token works for Facebook comments via fb.api in engage)."""
    penv = _penv(env)
    r = ig.api(penv, "POST", f"{penv['FB_PAGE_ID']}/messages", {"recipient": json.dumps({"comment_id": str(comment_id)}), "message": json.dumps({"text": text})})
    return str(r.get("message_id") or r.get("id") or "")


def react_instagram_dm(env: dict, user_id: str, message_id: str, reaction: str = REACTION) -> None:
    penv = _penv(env)
    ig.api(penv, "POST", f"{penv['FB_PAGE_ID']}/messages", {"recipient": json.dumps({"id": str(user_id)}), "sender_action": "react",
                                                           "payload": json.dumps({"message_id": str(message_id), "reaction": reaction})})


def react_messenger_dm(env: dict, user_id: str, message_id: str, reaction: str = REACTION) -> None:
    import fb
    fb.need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
    fb.api(env, "POST", f"{env['FB_PAGE_ID']}/messages", {"recipient": json.dumps({"id": str(user_id)}), "sender_action": "react",
                                                         "payload": json.dumps({"message_id": str(message_id), "reaction": reaction})})


def private_reply_facebook(env: dict, comment_id: str, text: str) -> str:
    import fb
    fb.need(env, "FB_PAGE_ID", "FB_PAGE_TOKEN")
    r = fb.api(env, "POST", f"{env['FB_PAGE_ID']}/messages", {"recipient": json.dumps({"comment_id": str(comment_id)}), "message": json.dumps({"text": text})})
    return str(r.get("message_id") or r.get("id") or "")


def ice_payload(cfg: dict) -> list[dict]:
    qs = [{"question": b["question"], "payload": f"ICE_{i + 1}"} for i, b in enumerate(cfg.get("ice_breakers", [])[:ICE_MAX])]
    return [{"call_to_actions": qs, "locale": "default"}]


def problems(cfg: dict) -> list[str]:
    """Static checks of the config: counts, lengths and the reply gates on every answer, welcome and private-reply text."""
    import engage
    out = []
    ib = cfg.get("ice_breakers", [])
    if len(ib) > ICE_MAX:
        out.append(f"{len(ib)} ice breakers (Meta allows {ICE_MAX})")
    for i, b in enumerate(ib):
        q = b.get("question", "")
        if not q or len(q) > ICE_Q_MAX:
            out.append(f"ice {i + 1}: question empty or over {ICE_Q_MAX} characters")
        if engage.has_tashkeel(q):
            out.append(f"ice {i + 1}: tashkeel in the question")
        for w in engage.reply_problems(b.get("answer", ""), relaxed=True):
            out.append(f"ice {i + 1} answer: {w}")
    for name, t in (("welcome", (cfg.get("welcome") or {}).get("text")), ("comment_to_dm", (cfg.get("comment_to_dm") or {}).get("text"))):
        if t:
            for w in engage.reply_problems(t, relaxed=True):
                out.append(f"{name}: {w}")
    return out


def apply(go: bool = False, root: Path | None = None, env: dict | None = None, api=None) -> dict:
    """Set the Instagram ice breakers. Dry unless go. Returns what is (or would be) sent."""
    cfg = load_config(root)
    bad = problems(cfg)
    payload = ice_payload(cfg)
    res = {"mode": "GO" if go else "DRY", "ice_breakers": [b["question"] for b in payload[0]["call_to_actions"]], "problems": bad, "set": False}
    if bad:
        res["status"] = "REFUSED: fix the config first"
        return res
    if not go:
        res["status"] = "DRY: would POST /{page-id}/messenger_profile platform=instagram with the questions above"
        return res
    env = env if env is not None else ig.load_env()
    penv = _penv(env)
    r = (api or ig.api)(penv, "POST", f"{penv['FB_PAGE_ID']}/messenger_profile", {"platform": "instagram", "ice_breakers": json.dumps(payload, ensure_ascii=False)})
    res.update(set=True, status="OK", api_result=r)
    return res


def status(root: Path | None = None, env: dict | None = None, live: bool = True, api=None) -> dict:
    cfg = load_config(root)
    out = {"config": str(config_path(root)), "ice_breakers": [b.get("question") for b in cfg["ice_breakers"]], "welcome": bool(welcome_for(cfg)),
           "keywords": (cfg.get("comment_to_dm") or {}).get("keywords", []), "problems": problems(cfg)}
    if live:
        try:
            env = env if env is not None else ig.load_env()
            penv = _penv(env)
            r = (api or ig.api)(penv, "GET", f"{penv['FB_PAGE_ID']}/messenger_profile", {"platform": "instagram", "fields": "ice_breakers"})
            out["live_ice_breakers"] = r.get("data", r)
        except (SystemExit, Exception) as e:     # noqa: BLE001  read only; the reason is shown without any credential
            out["live_ice_breakers"] = "not read: " + str(e)[:160]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Story-Wrap automatic DM features")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("apply")
    a_.add_argument("--go", action="store_true")
    s_ = sub.add_parser("status")
    s_.add_argument("--no-live", action="store_true")
    a = ap.parse_args(argv)
    res = apply(go=a.go) if a.cmd == "apply" else status(live=not a.no_live)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
