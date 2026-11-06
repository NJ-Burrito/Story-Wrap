

def test_owner_approval_finishes_an_episode_only_for_the_exact_score_and_video(tmp_path):
    # the owner 2026-10-27/28: E02 and E03 posted at critic 8 with heal/owner-approval.json bound to the critic's video
    import json as _j
    import loop_gate as LG
    w = tmp_path / "work" / "episodes" / "E09"
    (w / "heal").mkdir(parents=True)
    (w / "gate").mkdir()
    (w / "episode.mp4").write_bytes(b"x")
    (w / "gate" / "report.json").write_text(_j.dumps({"verdict": "PASS"}), encoding="utf-8")
    (w / "heal" / "critic.json").write_text(_j.dumps({"score": 8, "video_sha": "abc"}), encoding="utf-8")
    assert not LG.is_finished(tmp_path, "E09")
    (w / "heal" / "owner-approval.json").write_text(_j.dumps({"by": "the owner", "score": 8, "video_sha": "other"}), encoding="utf-8")
    assert not LG.is_finished(tmp_path, "E09")
    (w / "heal" / "owner-approval.json").write_text(_j.dumps({"by": "the owner", "score": 7, "video_sha": "abc"}), encoding="utf-8")
    assert not LG.is_finished(tmp_path, "E09")
    (w / "heal" / "owner-approval.json").write_text(_j.dumps({"by": "the owner", "score": 8, "video_sha": "abc"}), encoding="utf-8")
    assert LG.is_finished(tmp_path, "E09")
