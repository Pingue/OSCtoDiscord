# OSCtoDiscord

OSC to Discord bridge. Listens for OSC messages and posts a **predefined**
message to one Discord channel, defined in a config file. Each message can be
plain text, or text with an embedded picture or video. Sister project to
[OSCtoAtem](https://github.com/Pingue/OSCtoAtem) and
[OSCtoTwitch](https://github.com/Pingue/OSCtoTwitch).

## Setup

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # set `channel_id` and your messages
```

### Discord credentials

You need a **bot token**:

1. Create an application at <https://discord.com/developers/applications> → *New Application*.
2. *Bot* tab → *Reset Token* and copy it.
3. *OAuth2 → URL Generator*: scope `bot`, permissions *View Channel*, *Send Messages*,
   *Embed Links*, *Attach Files*. Open the generated URL to add the bot to your server.
4. Get the channel id: Discord *User Settings → Advanced → Developer Mode*, then
   right-click the channel → *Copy Channel ID*. Put it in `config.yaml` as `channel_id`.

Supply the token via `--bot-token` or the environment (or a gitignored `.env`
file next to the script, see `.env.example`):

| Env var | Required | Purpose |
|---|---|---|
| `DISCORD_BOT_TOKEN` | yes | Bot token |

Keep it secret; anyone with it can post as the bot.

## Run

```bash
DISCORD_BOT_TOKEN=xxxx python osctodiscord.py --port 1339 --config config.yaml
```

## Messages

Under `messages:` in the config, map an OSC address to what should be posted:

```yaml
messages:
  /discord/starting:
    content: "Stream is starting!"            # plain text
  /discord/live:
    content: "We're live!"
    image: https://example.com/banner.png     # embedded picture
  /discord/highlight:
    content: "Highlight of the night"
    video: https://example.com/clip.mp4       # video
  /discord/scene:
    content: "Now showing: {0}"               # {0}, {1}, ... = OSC arguments
  /discord/brb: "BRB"                         # bare string = plain text
```

### Ad-hoc message: `/discord/say`

`/discord/say <message> [image-or-video]` posts whatever you send, no config
entry needed. The second argument is optional and can be a URL or a local file
path; it's treated as an image if it ends in `.png`, `.jpg`, `.jpeg`, `.gif` or
`.webp`, and as a video otherwise (including links like YouTube).

```bash
oscsend 127.0.0.1 1339 /discord/say s "Hello everyone"
oscsend 127.0.0.1 1339 /discord/say ss "Look at this" "https://example.com/pic.png"
oscsend 127.0.0.1 1339 /discord/say ss "Replay" "https://example.com/clip.mp4"
```

For the config-defined messages above, `content`, `image` and `video` are each optional, but at least one is required.
`image` and `video` can be a URL or a path to a local file (local files are
uploaded; max 10MB).

Notes on how media is shown:

- **Image**: shown as an embed image.
- **Video**: Discord doesn't let bots create video embeds. A video **URL** is added
  to the message so Discord unfurls it (direct links to `.mp4`/`.webm`, YouTube etc.
  get a player); a **local file** is uploaded and plays inline.

Content is capped at 2000 characters (Discord's limit).

### Testing locally

```bash
oscsend 127.0.0.1 1339 /discord/starting
oscsend 127.0.0.1 1339 /discord/scene s "Main camera"
```

Use `127.0.0.1`, not `localhost` — the server binds to IPv4 only, and
`localhost` may resolve to the IPv6 `::1` on some systems, silently dropping
the packet.

## Tests

```bash
pip install pytest && pytest
```
