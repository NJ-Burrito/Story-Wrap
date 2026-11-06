# 🩹 Healing loop (no more notes from the owner)

the owner, 2026-10-23: "no more of my notes; learn from your work." The pipeline now catches what his notes used to catch, fixes it at the root, and remembers it. He sees work only after it heals clean.

Setting: `pipelines/heal.json` (on by default). Tool: `uv run tools/heal.py`. Questions: `kb/quality/critic-checklist.md`. Fixes: `kb/quality/heal-playbooks.md`. Memory: `kb/lessons/ledger.jsonl`.

## 🔁 The loop

```
gate ─► critic ─► classify ─► fix ─► rerun ─► gate ─► (critic again) ─► learn ─► show the owner
  ▲                                                         │
  └────────── not clean? next round (3 at most) ◄───────────┘
```

| # | Step | Who | Writes |
|---|---|---|---|
| 1 | **Gate.** The stage's own gates run (`shot.py all`, `compose.py all`, `artbook.py check`). The optional `heal` stage runs last and prints what is still needed. | Sonnet crew member (gate runner) | `gate/report.json`, `heal/classified.json`, `heal/critic-brief.md` |
| 2 | **Gather.** Review sheets, 8 to 12 raw frames, reference sheets. | Sonnet crew member (gatherer) | `review/*.png` |
| 3 | **Critic.** Reads the sheets and frames and answers every question of the checklist that applies, with evidence, and scores 1 to 10. | Sonnet critic (high effort) | `heal/critic.json` |
| 4 | **Validate and classify.** `heal.py classify <dir>` validates the critic (all questions answered, evidence given, score not above the rubric) and maps every gate failure and critic fault to a class, a fix place, a fixer and a rerun stage. | script | `heal/classified.json`, `heal/fix-brief.md` |
| 5 | **Fix.** One class at a time, at the root, where the playbook says. Every agent is Sonnet 5.5 (owner, 2026-10-23), a crew member from `.claude/agents/sw-*.md`: the artist or writer crew member for creative faults (drawing, catalogue art, choreography, writing), the tooling one for tool faults (gate, wiring, preview, episode files). Each fix is recorded with `heal.py round`. | Sonnet crew member (artist, writer or tooling, by fault class) | the fixed source, `heal/rounds.jsonl` |
| 6 | **Rerun.** From the class's `rerun_from` stage; the stage hashes rerun everything that read a changed file. Then the gates again, then a fresh critic. | Sonnet gate runner | fresh outputs |
| 7 | **Learn.** `heal.py learn <dir>` appends each healed fault to the ledger. A new kind of fault also writes `kb/lessons/proposals/P-*.md` (rule text, check design, test idea). | script, then the Lead | `kb/lessons/` |
| 8 | **Show the owner.** Only when `heal.py status <dir>` says ready (below). | the Lead | one new tab in `previews/index.html` |

Voice: Chatterbox, one take per line (Google Gemini is banned); the critic checks the voiced episode and a heal never re-voices a line. A voice fault is fixed at its source (the reference, the cast record, the chain profile; [VOICE.md](VOICE.md) "Casting order", `bible/sound/SOUND.md` §10), never by hand gain on one take; a take generated over the pause limit is regenerated as a new line (`retext`), the chain's pause floor (R-472) cannot fix it. The Lead dispatches and ends its turn (no polling); each agent returns a receipt of 15 lines or fewer, the detail is in the files above. Workers never instruct each other. Agents commit only on their own branch; the Lead merges proposals and pushes.

## ✅ When the owner is shown work

All of these, checked by `heal.py status` (exit 0):
- every gate in the report passes, none skipped (`GATE-INCOMPLETE` is a fault);
- `heal/critic.json` is valid and the score is **9 or more** (the owner's scale: v2 = 6, art book first pass = 8, v5 and shot 2 = 10);
- no open critic fault of class S1, S2 or S3;
- `heal.py guard` is clean: no threshold, check, schema, reference or trace touched.

Not ready means he is not shown it. Not even as "almost done".

## ⛔ When the budget runs out

Limits in `heal.json`: 3 rounds per stage, 9 fix dispatches, 180 minutes, 4,000,000 tokens per build. The next `heal.py round` past a limit exits 3 and writes `heal/STOPPED.md`: every remaining fault, its class, its evidence. Then:
- stop and report the remaining faults to the Lead and the owner in plain words;
- **never** loosen a gate, skip a check or raise the score by hand;
- **never** present the work as done.

## 🚫 Forbidden fixes (the guard refuses them, exit 4)

`loosen_threshold`, `edit_trace`, `hide_from_camera`, `skip_check`, `widen_exemption`, `edit_approved_version`, `hand_edit_output`. `heal.py` snapshots the frozen files (`tools/qg_checks.py`, `tools/quality_gate.py`, schemas, `reference/**`, `pipelines/heal.json`, the checklist) when the heal starts and refuses any round after one changed. Traces, masks and gate outputs may change only by re-running their stage. A threshold moves only under R-212 as a Lead-merged proposal with a measured sample, never inside a heal.

## 🧠 Learning

- Every healed fault: one line in `kb/lessons/ledger.jsonl` (date, build, fault, root cause, fix, rule id, check id). Seeded with 32 past faults.
- A fault no class or check knows (`UNKNOWN`, a critic `NEW`, a `GATE-BLIND` gap): a proposal in `kb/lessons/proposals/`. The Lead merges it into `kb/rulebook.md`, `qg_checks.py` (with a test) and the checklist, then the class table. Next build, that fault is caught by a gate, not by the owner.
- The checklist and playbooks grow only this way; a critic never edits them.

- The **build retro** (`learn.py retro`, daily stage after `critic`) reads the heal rounds, gate failures and critic notes of each episode and writes lessons to the same ledger (`source: retro`), the craft playbook `kb/playbook.md` and proposals; the **audience review** adds findings 14 h after each post. They never change a gate, and a gate proposal may only get stricter. See `LEARN.md`.

## 🧰 Commands

| Command | Does |
|---|---|
| `heal.py prepare <dir>` | snapshot + classify + briefs (what `shot.py heal`, `compose.py heal`, `artbook.py heal` call) |
| `heal.py classify <dir>` | read the gate report and `critic.json`, map every fault; exit 0 only when ready |
| `heal.py critic-brief <dir>` / `fix-brief <dir>` | inputs for the critic and the fixer |
| `heal.py validate-critic <dir>` | refuse an incomplete or inflated `critic.json` |
| `heal.py round <dir> --fault G-001 --fix "..." --fix-kind catalogue --files a b --result fixed [--new-round] [--tokens N]` | record one fix; enforces the limits and the guard |
| `heal.py guard <dir>` | list forbidden changes since the snapshot |
| `heal.py learn <dir> [--build ID]` | ledger and proposals |
| `heal.py status <dir>` | open faults, rounds, budget, ready or not |

`<dir>` is the shot folder, `work/episodes/<ep>`, or `work/artbook` for the art book. Tests: `tools/tests/test_heal.py`.

## 🔗 Where it fits

Stage docs: `RUNBOOK.md` (shot), `COMPOSE.md` (episode), `ARTBOOK.md` (sketch), `WRITING.md`, `VOICE.md`. Each has a "Healing" section. This overrides R-012 "run once, no retries" for Story-Wrap builds (proposal `kb/lessons/proposals/P-0001-heal-loop-rule.md`); the deterministic gates still run every time and are never loosened.

> Crew: the critic is `.claude/agents/sw-critic.md`, fixes go to `sw-healer` (tool faults: `sw-pipeline-engineer`; creative faults: the owning artist or director). All Sonnet 5.5. See pipelines/CREW.md.

