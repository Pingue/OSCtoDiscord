import os
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse
import structlog

from discord_client import DiscordChannel

MessageSpec = Union[str, Dict[str, str]]

SAY_ADDRESS = "/discord/say"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def media_kind(media: str) -> str:
    """'image' for known picture extensions; anything else (mp4, YouTube links...) is 'video'."""
    path = urlparse(media).path if media.startswith(("http://", "https://")) else media
    return "image" if os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS else "video"


class Mapper:
    """Maps OSC addresses to predefined Discord messages for one channel."""

    def __init__(self, discord: DiscordChannel, channel_id: str,
                 messages: Optional[Dict[str, MessageSpec]] = None):
        self.discord = discord
        self.channel_id = str(channel_id)
        self.messages = {addr: self._normalise(spec) for addr, spec in (messages or {}).items()}
        self.logger = structlog.get_logger("mapper")

    @staticmethod
    def _normalise(spec: MessageSpec) -> Dict[str, str]:
        if isinstance(spec, str):
            return {"content": spec}
        return {k: spec[k] for k in ("content", "image", "video") if spec.get(k)}

    def build_message(self, address: str, args: List[Any]) -> Optional[Dict[str, str]]:
        """Return {content, image, video} for an OSC address, or None if unknown/unusable."""
        if address == SAY_ADDRESS:
            return self._build_say(args)
        spec = self.messages.get(address)
        if spec is None:
            return None
        if not spec:
            self.logger.error("Message has no content, image or video", address=address)
            return None
        result = dict(spec)
        if "content" in result:
            try:
                result["content"] = result["content"].format(*args)
            except IndexError:
                self.logger.error("Not enough OSC arguments for template",
                                  address=address, template=spec["content"], args=args)
                return None
        return result

    def _build_say(self, args: List[Any]) -> Optional[Dict[str, str]]:
        """/discord/say <message> [image-or-video]"""
        if not args:
            self.logger.error("/discord/say needs a message argument")
            return None
        result = {}
        content = str(args[0]).strip()
        if content:
            result["content"] = content
        if len(args) > 1 and str(args[1]).strip():
            media = str(args[1]).strip()
            result[media_kind(media)] = media
        return result or None

    def handle_osc_message(self, address: str, *args: Any) -> None:
        self.logger.info("OSC message received", address=address, args=args)
        message = self.build_message(address, list(args))
        if message is None:
            self.logger.warning("No Discord message produced for OSC message", address=address)
            return
        try:
            self.discord.send_message(self.channel_id, **message)
        except Exception as e:
            self.logger.error("Failed to send Discord message", address=address,
                              error=str(e), error_type=type(e).__name__)
