"""Inbox harvest tests: no network (ig._http is replaced), no real credentials, no real LinkedIn repo."""
import csv
import json

import pytest

import fb
import ig
import inbox
import yt

TOK, PUB, PAGE = "IGQWRtoken111111111", "EAAPUBtoken2222222222", "EAAPAGEtoken33333333"
ENV = {"IG_USER_ID": "1784", "IG_USERNAME": "story_account", "IG_ACCESS_TOKEN": TOK, "IG_PUBLISH_TOKEN": PUB, "FB_PAGE_ID": "555", "FB_PAGE_TOKEN": PAGE}


class Graph:
    """Answers like graph.instagram.com / graph.facebook.com for the edges inbox.py reads; records every call (method, url, headers)."""
    def __init__(self, bad=()):
        self.calls, self.bad = [], bad

    def __call__(self, method, url, headers=None, data=None):
        self.calls.append((method, url, dict(headers or {})))
        u = url.split("?")[0]
        for b in self.bad:
            if b in u:
                raise RuntimeError(f"HTTP 400 GET {u}: nope access_token={TOK}")
        if u.endswith("/555/conversations"):
            if "platform=instagram" in url:
                return {"data": [{"id": "t_ig1", "updated_time": "2026-10-26T10:00:00+0000", "messages": {"data": [
                    {"id": "m2", "from": {"id": "1784", "username": "story_account"}, "message": "أهلا بك", "created_time": "2026-10-26T10:00:00+0000"},
                    {"id": "m1", "from": {"id": "u9", "username": "sara"}, "message": "مرحبا، متى الحلقة؟", "created_time": "2026-10-26T09:00:00+0000",
                     "attachments": {"data": [{"id": "a", "mime_type": "image/jpeg", "name": "x.jpg", "image_data": {"url": "https://cdn/secret"}}]}}],
                    "paging": {"next": "https://graph.facebook.com/v26.0/t_ig1/messages?after=M"}}}]}
            return {"data": [{"id": "t_m1", "updated_time": "2026-10-25T08:00:00+0000", "messages": {"data": [
                {"id": "mm1", "from": {"id": "u7", "name": "Omar"}, "message": "=HYPERLINK(1)", "created_time": "2026-10-25T08:00:00+0000"}]}}]}
        if u.endswith("/t_ig1/messages"):
            return {"data": [{"id": "m0", "from": {"id": "u9", "username": "sara"}, "message": "hello there", "created_time": "2026-10-26T08:00:00+0000"}]}
        if u.endswith("/1784/media"):
            return {"data": [{"id": "M1", "permalink": "https://instagram.com/reel/abc/", "timestamp": "2026-10-20T10:00:00+0000"}]}
        if u.endswith("/M1/comments"):
            return {"data": [{"id": "c1", "text": "قصة حلوة", "timestamp": "2026-10-26T11:00:00+0000", "username": "layla"}]}
        if u.endswith("/c1/replies"):
            return {"data": [{"id": "c1r", "text": "شكرا", "timestamp": "2026-10-26T12:00:00+0000", "username": "story_account"}]}
        if u.endswith("/555/posts"):
            return {"data": [{"id": "p1", "permalink_url": "https://fb.com/p1", "created_time": "2026-10-20T10:00:00+0000"}]}
        if u.endswith("/555/video_reels"):
            return {"data": [{"id": "p1", "permalink_url": "https://fb.com/p1"}, {"id": "v2", "permalink_url": "https://fb.com/v2"}]}
        if u.endswith("/p1/comments"):
            return {"data": [{"id": "f1", "message": "Nice", "created_time": "2026-10-26T13:00:00+0000", "from": {"id": "u1", "name": "Ali"}}]}
        if u.endswith("/v2/comments"):
            return {"data": []}
        if u.endswith("/f1/comments"):
            return {"data": [{"id": "f1r", "message": "Thanks", "created_time": "2026-10-26T14:00:00+0000", "from": {"id": "555", "name": "StoryPage"}}]}
        raise AssertionError("unexpected call " + url)


class Req:
    def __init__(self, items, nxt=None):
        self.items, self.nxt = items, nxt

    def execute(self):
        return {"items": self.items, **({"nextPageToken": self.nxt} if self.nxt else {})}


class YtFake:
    def commentThreads(self):
        outer = self

        class T:
            def list(self, **kw):
                top = {"id": "y1", "snippet": {"topLevelComment": {"id": "y1", "snippet": {"videoId": "vid1", "authorDisplayName": "Hana", "authorChannelId": {"value": "UCx"},
                                                                                           "textOriginal": "Great", "publishedAt": "2026-10-26T15:00:00Z"}}, "totalReplyCount": 6},
                       "replies": {"comments": []}}
                return Req([top])
        return T()

    def comments(self):
        class C:
            def list(self, **kw):
                import yt
                return Req([{"id": "y1.r", "snippet": {"videoId": "vid1", "authorDisplayName": "NJ", "authorChannelId": {"value": yt.CHANNEL_ID},
                                                       "textOriginal": "Thank you", "publishedAt": "2026-10-26T16:00:00Z"}}])
        return C()


def make_li(tmp_path):
    li = tmp_path / "li"
    (li / "engage").mkdir(parents=True, exist_ok=True)
    (li / "published").mkdir(exist_ok=True)
    (li / "published" / "ledger.jsonl").write_text(json.dumps({"slug": "s1", "url": "https://linkedin.com/feed/update/urn:li:share:1/", "urn": "urn:li:share:1"}) + "\n", encoding="utf-8")
    (li / "engage" / "replies-s1.md").write_text(
        "\n## 2026-10-12 16:03\n- **Abdelhalim A.**: Great perspective!\n  - replied: Thanks Abdelhalim.\n- **Noor**: سؤال جيد\n  - for you to post (board, Comments to post): hi\n"
        "- Skipped Person: skipped (not worth a reply)\n", encoding="utf-8")
    (li / "published" / "comments.jsonl").write_text(json.dumps({"at": "2026-10-10T12:40:08+03:00", "post": "urn:li:ugcPost:9", "url": "https://x/p", "author": "David", "text": "My comment",
                                                               "comment_urn": "777", "kind": "engage"}) + "\n", encoding="utf-8")
    return li


@pytest.fixture
def graph(monkeypatch):
    g = Graph()
    monkeypatch.setattr(ig, "_http", g)
    return g


def run(tmp_path, only=None, **kw):
    li = make_li(tmp_path)
    return inbox.cmd_harvest(repo=tmp_path, env=dict(ENV), only=only, linkedin_root=li, yt_service=YtFake(), **kw), tmp_path / "work" / "inbox"


def test_all_sources_land_in_csv_sorted_with_bom_and_amman_time(tmp_path, graph, capsys):
    rc, d = run(tmp_path)
    assert rc == 0
    raw = (d / "inbox.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader((d / "inbox.csv").open(encoding="utf-8-sig", newline="")))
    assert list(rows[0]) == list(inbox.COLUMNS)
    stamps = [r["created_at_utc"] for r in rows]
    assert stamps == sorted(stamps, reverse=True)
    plats = {r["platform"] for r in rows}
    assert plats == {"instagram", "facebook", "youtube", "linkedin"}
    dm = next(r for r in rows if r["message_id"] == "m1")
    assert dm["created_at_utc"] == "2026-10-26T09:00:00Z" and dm["created_at_amman"] == "2026-10-26T12:00:00+03:00"
    assert dm["kind"] == "dm" and dm["sender_name"] == "sara" and dm["language"] == "ar" and dm["attachments"] == "image/jpeg:x.jpg" and "cdn" not in dm["attachments"]
    out = capsys.readouterr().out
    assert "OK instagram_dm: 3 rows read" in out and "مرحبا" not in out and "Great perspective" not in out


def test_dm_paging_follows_messages_edge_and_reply_flag(tmp_path, graph):
    rc, d = run(tmp_path, only=["instagram_dm"])
    rows = {r["message_id"]: r for r in inbox.load_rows(d)}
    assert set(rows) == {"m0", "m1", "m2"}
    assert rows["m2"]["is_own"] is True and rows["m1"]["replied_by_us"] is True and rows["m0"]["replied_by_us"] is True and rows["m2"]["replied_by_us"] is False
    first = graph.calls[0]
    assert first[2]["Authorization"] == f"Bearer {PUB}" and first[1].startswith("https://graph.facebook.com/") and "platform=instagram" in first[1]
    assert all(c[0] == "GET" for c in graph.calls)       # read only


def test_messenger_uses_same_token_and_formula_text_is_neutralised_in_csv(tmp_path, graph):
    rc, d = run(tmp_path, only=["facebook_dm"])
    assert "platform=messenger" in graph.calls[0][1] and graph.calls[0][2]["Authorization"] == f"Bearer {PUB}"
    assert inbox.load_rows(d)[0]["text"] == "=HYPERLINK(1)"
    csv_row = list(csv.DictReader((d / "inbox.csv").open(encoding="utf-8-sig", newline="")))[0]
    assert csv_row["text"] == "'=HYPERLINK(1)" and csv_row["platform"] == "facebook" and csv_row["sender_name"] == "Omar"


def test_instagram_comments_with_replies_and_own_flag(tmp_path, graph):
    rc, d = run(tmp_path, only=["instagram_comments"])
    rows = {r["message_id"]: r for r in inbox.load_rows(d)}
    assert rows["c1"]["kind"] == "comment" and rows["c1"]["replied_by_us"] is True and rows["c1"]["post_url"].endswith("/abc/")
    assert rows["c1r"]["kind"] == "reply" and rows["c1r"]["is_own"] is True and rows["c1r"]["parent_id"] == "c1"
    assert graph.calls[0][2]["Authorization"] == f"Bearer {PUB}" and graph.calls[0][1].startswith("https://graph.facebook.com/")      # Page token first (Facebook-login media)


def test_instagram_comments_page_token_null_username_and_login_fallback(tmp_path, monkeypatch):
    class G(Graph):
        def __call__(self, method, url, headers=None, data=None):
            u = url.split("?")[0]
            if "graph.facebook.com" in url and u.endswith("/M1/comments"):
                assert "from" in url                      # `from` rides on the Page route only
                return {"data": [{"id": "p1", "text": "من هذا", "timestamp": "2026-10-26T11:00:00+0000", "username": None, "from": None},
                                 {"id": "p2", "text": "سؤال", "timestamp": "2026-10-26T11:05:00+0000", "from": {"id": "u55"}},
                                 {"id": "p3", "text": "ردنا", "timestamp": "2026-10-26T11:09:00+0000", "from": {"id": "1784"}}]}
            if u.endswith("/p1/replies") or u.endswith("/p2/replies") or u.endswith("/p3/replies"):
                return {"data": []}
            if "graph.instagram.com" in url and u.endswith("/M1/comments"):
                raise AssertionError("the login host must not be used when the Page read works")
            return super().__call__(method, url, headers, data)
    g = G()
    monkeypatch.setattr(ig, "_http", g)
    rc, d = run(tmp_path, only=["instagram_comments"])
    rows = {r["message_id"]: r for r in inbox.load_rows(d)}
    assert rows["p1"]["sender_name"] == "unknown" and rows["p1"]["sender_id"] == "" and rows["p1"]["is_own"] is False
    assert rows["p2"]["sender_id"] == "u55" and rows["p3"]["is_own"] is True        # own account recognised by from.id
    # Page route failing -> the Instagram-login token answers
    class H(Graph):
        def __call__(self, method, url, headers=None, data=None):
            if "graph.facebook.com" in url and "/1784/media" in url:
                raise RuntimeError("HTTP 400 GET x: (#10) nope")
            return super().__call__(method, url, headers, data)
    monkeypatch.setattr(ig, "_http", H())
    rc, d = run(tmp_path / "b", only=["instagram_comments"])
    assert {"c1", "c1r"} <= {r["message_id"] for r in inbox.load_rows(d)}
    # no IG_PUBLISH_TOKEN -> the login route only
    g2 = Graph()
    monkeypatch.setattr(ig, "_http", g2)
    env = {k: v for k, v in ENV.items() if k != "IG_PUBLISH_TOKEN"}
    inbox.cmd_harvest(repo=tmp_path / "c", env=env, only=["instagram_comments"])
    assert all("graph.instagram.com" in c[1] for c in g2.calls)


def test_facebook_comments_dedup_posts_across_edges(tmp_path, graph):
    rc, d = run(tmp_path, only=["facebook_comments"])
    rows = inbox.load_rows(d)
    assert sorted(r["message_id"] for r in rows) == ["f1", "f1r"]
    assert sum(1 for c in graph.calls if c[1].split("?")[0].endswith("/p1/comments")) == 1      # p1 is on both edges, read once
    assert next(r for r in rows if r["message_id"] == "f1r")["is_own"] is True and next(r for r in rows if r["message_id"] == "f1")["replied_by_us"] is True


def test_youtube_fetches_overflow_replies(tmp_path, graph):
    rc, d = run(tmp_path, only=["youtube_comments"])
    rows = {r["message_id"]: r for r in inbox.load_rows(d)}
    assert set(rows) == {"y1", "y1.r"} and rows["y1.r"]["is_own"] is True and rows["y1"]["replied_by_us"] is True
    assert rows["y1"]["post_url"] == "https://www.youtube.com/watch?v=vid1&lc=y1" and rows["y1"]["language"] == "en"


def test_linkedin_reads_files_only(tmp_path, graph):
    rc, d = run(tmp_path, only=["linkedin"])
    rows = inbox.load_rows(d)
    assert graph.calls == []
    texts = {r["text"] for r in rows}
    assert {"Great perspective!", "Thanks Abdelhalim.", "سؤال جيد", "My comment"} <= texts
    assert "hi" not in texts and not any("skipped" in t for t in texts)         # a draft waiting for the owner is not a reply we sent
    inb = next(r for r in rows if r["text"] == "Great perspective!")
    assert inb["replied_by_us"] is True and inb["created_at_amman"] == "2026-10-12T16:03:00+03:00" and inb["post_url"].startswith("https://linkedin.com/feed")
    assert next(r for r in rows if r["text"] == "سؤال جيد")["replied_by_us"] is False


def test_dedup_and_incremental_merge_keep_first_harvest_time(tmp_path, graph):
    run(tmp_path, only=["instagram_comments"])
    d = tmp_path / "work" / "inbox"
    first = {r["message_id"]: r["harvested_at"] for r in inbox.load_rows(d)}
    st = json.loads((d / "state.json").read_text(encoding="utf-8"))
    assert st["sources"]["instagram_comments"]["status"] == "ok"
    rc, _ = run(tmp_path, only=["instagram_comments"], since_days=30)
    rows = inbox.load_rows(d)
    assert len(rows) == 2 and {r["message_id"]: r["harvested_at"] for r in rows} == first


def test_merge_function_dedups_by_platform_and_id():
    a = inbox.row("comment", "instagram", "a", "t", "", "1", "", "x", "", False, "2026-10-26T10:00:00Z", "one")
    b = inbox.row("comment", "facebook", "a", "t", "", "1", "", "x", "", False, "2026-10-26T11:00:00Z", "two")
    rows, added = inbox.merge([a], [dict(a, text="changed"), b])
    assert added == 1 and len(rows) == 2 and rows[0]["platform"] == "facebook" and next(r for r in rows if r["platform"] == "instagram")["text"] == "changed"


def test_one_source_fails_alone_exit_zero_and_error_redacted(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ig, "_http", Graph(bad=("/555/conversations",)))
    rc, d = run(tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert "FAIL instagram_dm" in out and "FAIL facebook_dm" in out and "OK linkedin" in out and "OK youtube_comments" in out
    assert TOK not in out and PUB not in out and PAGE not in out and "[REDACTED]" in out
    assert TOK not in (d / "state.json").read_text(encoding="utf-8")
    assert json.loads((d / "state.json").read_text(encoding="utf-8"))["sources"]["instagram_dm"]["status"] == "FAIL"


def test_all_sources_failing_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ig, "_http", Graph())
    monkeypatch.setattr(yt, "TOKEN_FILE", tmp_path / "no-youtube-token.json")   # never the real token on this PC
    rc = inbox.cmd_harvest(repo=tmp_path, env={}, linkedin_root=tmp_path / "nolinkedin")
    out = capsys.readouterr().out
    assert rc == 2 and out.count("FAIL ") == 6


def test_dry_writes_nothing(tmp_path, graph, capsys):
    rc, d = run(tmp_path, dry=True)
    assert rc == 0 and not d.exists() and "DRY:" in capsys.readouterr().out


def test_status_prints_counts_never_text(tmp_path, graph):
    run(tmp_path)
    s = inbox.cmd_status(tmp_path)
    assert "unanswered" in s and "instagram" in s and "مرحبا" not in s and "Great" not in s


def test_language_guess():
    assert inbox.lang_guess("مرحبا hi") == "ar" and inbox.lang_guess("hello world مرحبا") == "en" and inbox.lang_guess("12 !!") == "" and inbox.lang_guess("Привет") == "other"


def test_scrub_removes_every_credential_form():
    s = inbox.scrub(f"x {TOK} y access_token=ABCDEF Bearer abcdefghijkl1234", {"IG_ACCESS_TOKEN": TOK})
    assert TOK not in s and "ABCDEF" not in s and "abcdefghijkl1234" not in s
