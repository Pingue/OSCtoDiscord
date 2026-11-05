import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from unittest.mock import MagicMock
import pytest
from mapper import Mapper
from discord_client import DiscordChannel, DiscordError


def resp(status, payload=None):
    r = MagicMock(); r.status_code = status; r.json.return_value = payload or {}; r.text = str(payload)
    return r


def test_mapper_templates_and_unknown():
    dc = MagicMock()
    m = Mapper(dc, 123, {
        "/d/plain": "hello",
        "/d/scene": {"content": "Now: {0}"},
        "/d/pic": {"content": "live", "image": "http://x/y.png"},
        "/d/gg": {"content": "GG!", "reactions": ["🎉", "🔥"]},
        "/d/empty": {},
    })
    m.handle_osc_message("/d/plain")
    dc.send_message.assert_called_with("123", content="hello")
    m.handle_osc_message("/d/scene", "Main")
    dc.send_message.assert_called_with("123", content="Now: Main")
    m.handle_osc_message("/d/pic")
    dc.send_message.assert_called_with("123", content="live", image="http://x/y.png")
    m.handle_osc_message("/d/gg")
    dc.send_message.assert_called_with("123", content="GG!", reactions=["🎉", "🔥"])
    dc.reset_mock()
    m.handle_osc_message("/d/scene")     # missing arg
    m.handle_osc_message("/unknown", 1)
    m.handle_osc_message("/d/empty")
    dc.send_message.assert_not_called()


def test_send_plain_and_image_url():
    s = MagicMock(); s.request.return_value = resp(200)
    d = DiscordChannel("tok", session=s)
    d.send_message("9", "hi")
    call = s.request.call_args
    assert call.args[:2] == ("POST", "https://discord.com/api/v10/channels/9/messages")
    assert call.kwargs["json"] == {"content": "hi"}
    assert call.kwargs["headers"]["Authorization"] == "Bot tok"
    d.send_message("9", "hi", image="https://x/y.png")
    assert s.request.call_args.kwargs["json"]["embeds"] == [{"image": {"url": "https://x/y.png"}}]


def test_video_url_is_appended_to_content():
    s = MagicMock(); s.request.return_value = resp(200)
    DiscordChannel("tok", session=s).send_message("9", "watch", video="https://x/v.mp4")
    assert s.request.call_args.kwargs["json"]["content"] == "watch\nhttps://x/v.mp4"


def test_local_files_are_uploaded(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"png")
    vid = tmp_path / "b.mp4"; vid.write_bytes(b"mp4")
    s = MagicMock(); s.request.return_value = resp(200)
    DiscordChannel("tok", session=s).send_message("9", "x", image=str(img), video=str(vid))
    kw = s.request.call_args.kwargs
    payload = json.loads(kw["data"]["payload_json"])
    assert payload["embeds"][0]["image"]["url"] == "attachment://a.png"
    assert [a["filename"] for a in payload["attachments"]] == ["a.png", "b.mp4"]
    assert set(kw["files"]) == {"files[0]", "files[1]"}


def test_errors(tmp_path):
    s = MagicMock()
    d = DiscordChannel("tok", session=s)
    with pytest.raises(DiscordError):
        d.send_message("9", "  ")                       # empty
    with pytest.raises(DiscordError):
        d.send_message("9", "x", image="/no/such.png")  # missing file
    s.request.return_value = resp(403, {"message": "Missing Access"})
    with pytest.raises(DiscordError):
        d.send_message("9", "x")
    s.request.return_value = resp(401)
    with pytest.raises(DiscordError):
        d.validate("9")


def test_reactions_are_added_after_send():
    s = MagicMock(); s.request.return_value = resp(200, {"id": "42"})
    d = DiscordChannel("tok", session=s)
    d.send_message("9", "gg", reactions=["🎉", "fire:1"])
    calls = s.request.call_args_list
    assert calls[0].args[:2] == ("POST", "https://discord.com/api/v10/channels/9/messages")
    assert calls[1].args[:2] == ("PUT", "https://discord.com/api/v10/channels/9/messages/42/reactions/%F0%9F%8E%89/@me")
    assert calls[2].args[:2] == ("PUT", "https://discord.com/api/v10/channels/9/messages/42/reactions/fire%3A1/@me")


def test_rate_limit_retries_once(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    s = MagicMock(); s.request.side_effect = [resp(429, {"retry_after": 0.1}), resp(200)]
    DiscordChannel("tok", session=s).send_message("9", "x")
    assert s.request.call_count == 2


def test_say_address():
    dc = MagicMock()
    m = Mapper(dc, 1)
    m.handle_osc_message("/discord/say", "hello")
    dc.send_message.assert_called_with("1", content="hello")
    m.handle_osc_message("/discord/say", "pic", "https://x/a.PNG?v=1")
    dc.send_message.assert_called_with("1", content="pic", image="https://x/a.PNG?v=1")
    m.handle_osc_message("/discord/say", "clip", "/tmp/c.mp4")
    dc.send_message.assert_called_with("1", content="clip", video="/tmp/c.mp4")
    m.handle_osc_message("/discord/say", "yt", "https://youtu.be/abc")
    dc.send_message.assert_called_with("1", content="yt", video="https://youtu.be/abc")
    m.handle_osc_message("/discord/say", "", "b.jpg")
    dc.send_message.assert_called_with("1", image="b.jpg")
    dc.reset_mock()
    m.handle_osc_message("/discord/say")
    m.handle_osc_message("/discord/say", "")
    dc.send_message.assert_not_called()
