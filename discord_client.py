"""Minimal Discord client: posts messages to one channel via the REST API."""
import json
import mimetypes
import os
import time
from typing import List, Optional
from urllib.parse import quote

import requests
import structlog

API_URL = "https://discord.com/api/v10"
MAX_CONTENT_LENGTH = 2000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # default per-file limit for servers without boosts


class DiscordError(Exception):
    """Raised when talking to Discord fails."""


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


class DiscordChannel:
    """Sends messages to channels as a bot.

    Needs a bot token, and the bot must be in the server with the *View Channel*,
    *Send Messages* and (for embeds and uploads) *Embed Links* / *Attach Files*
    permissions on the target channel.
    """

    def __init__(self, bot_token: str, timeout: float = 15.0,
                 session: Optional[requests.Session] = None):
        self.bot_token = bot_token
        self.timeout = timeout
        self.session = session or requests.Session()
        self.logger = structlog.get_logger("discord")

    def _headers(self) -> dict:
        return {"Authorization": f"Bot {self.bot_token}"}

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        resp = self.session.request(method, f"{API_URL}{path}", headers=self._headers(),
                                    timeout=self.timeout, **kwargs)
        if resp.status_code == 429:  # rate limited: wait once, then retry
            retry_after = float(resp.json().get("retry_after", 1))
            self.logger.warning("Rate limited by Discord", retry_after=retry_after)
            time.sleep(min(retry_after, 30))
            resp = self.session.request(method, f"{API_URL}{path}", headers=self._headers(),
                                        timeout=self.timeout, **kwargs)
        return resp

    def validate(self, channel_id: str) -> None:
        """Check the token works and that the channel is visible to the bot."""
        me = self._request("GET", "/users/@me")
        if me.status_code != 200:
            raise DiscordError(f"Bot token rejected ({me.status_code}): {me.text}")
        self.bot_name = me.json().get("username")
        ch = self._request("GET", f"/channels/{channel_id}")
        if ch.status_code != 200:
            raise DiscordError(f"Cannot access channel {channel_id} ({ch.status_code}): {ch.text}")
        self.logger.info("Discord validated", bot=self.bot_name,
                         channel=ch.json().get("name"))

    def send_message(self, channel_id: str, content: str = "",
                     image: Optional[str] = None, video: Optional[str] = None,
                     reactions: Optional[List[str]] = None) -> None:
        """Post a message with optional text, picture, video and reactions.

        ``image`` / ``video`` may each be a URL or a path to a local file.

        - Image URL: shown as an embed image. Local image: uploaded and embedded.
        - Video: Discord does not let bots build video embeds, so a video URL is
          appended to the message (Discord unfurls it into a player) and a local
          video is uploaded as an attachment (which plays inline).
        """
        content = (content or "").strip()
        payload: dict = {}
        files = []  # (filename, bytes, mimetype)

        if image:
            if is_url(image):
                payload["embeds"] = [{"image": {"url": image}}]
            else:
                name, data, mime = self._read_file(image)
                files.append((name, data, mime))
                payload["embeds"] = [{"image": {"url": f"attachment://{name}"}}]
        if video:
            if is_url(video):
                content = f"{content}\n{video}".strip()
            else:
                files.append(self._read_file(video))

        if len(content) > MAX_CONTENT_LENGTH:
            self.logger.warning("Message truncated", length=len(content))
            content = content[:MAX_CONTENT_LENGTH]
        if content:
            payload["content"] = content
        if not payload and not files:
            raise DiscordError("Refusing to send an empty message")

        path = f"/channels/{channel_id}/messages"
        if files:
            payload["attachments"] = [{"id": i, "filename": f[0]} for i, f in enumerate(files)]
            resp = self._request("POST", path,
                                 data={"payload_json": json.dumps(payload)},
                                 files={f"files[{i}]": f for i, f in enumerate(files)})
        else:
            resp = self._request("POST", path, json=payload)
        if resp.status_code not in (200, 201):
            raise DiscordError(f"Send failed ({resp.status_code}): {resp.text}")
        self.logger.info("Discord message sent", channel_id=channel_id, content=content,
                         image=image, video=video)
        if reactions:
            message_id = resp.json()["id"]
            self.add_reactions(channel_id, message_id, reactions)

    def add_reactions(self, channel_id: str, message_id: str, emojis: List[str]) -> None:
        """Add one or more reactions to a message, in order.

        Each emoji is either a unicode character (e.g. "🔥") or a custom emoji
        in ``name:id`` form (e.g. "partyblob:123456789012345678").
        """
        for emoji in emojis:
            path = f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji)}/@me"
            resp = self._request("PUT", path)
            if resp.status_code not in (200, 201, 204):
                self.logger.error("Failed to add reaction", emoji=emoji,
                                  status=resp.status_code, response=resp.text)

    @staticmethod
    def _read_file(path: str):
        if not os.path.isfile(path):
            raise DiscordError(f"Media file not found: {path}")
        if os.path.getsize(path) > MAX_UPLOAD_BYTES:
            raise DiscordError(f"Media file is over the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB "
                               f"upload limit: {path}")
        with open(path, "rb") as f:
            data = f.read()
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return os.path.basename(path), data, mime
