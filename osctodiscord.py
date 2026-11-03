import click
import structlog
import yaml
from dotenv import load_dotenv
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

from discord_client import DiscordChannel
from mapper import Mapper

# Optionally read credentials from a .env file. Real environment variables win.
load_dotenv()


@click.command()
@click.option('--port', '-p', default=1339, type=int, help='Port to listen for OSC messages on (default: 1339)')
@click.option('--config', '-c', 'config_path', default='config.yaml', type=click.Path(exists=True),
              help='Path to YAML config file (default: config.yaml)')
@click.option('--bot-token', envvar='DISCORD_BOT_TOKEN', required=True,
              help='Discord bot token [env: DISCORD_BOT_TOKEN]')
def main(port, config_path, bot_token):
    """OSC to Discord Bridge - Receive OSC messages and post predefined messages to a Discord channel"""
    logger = structlog.get_logger("osctodiscord")

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
    channel_id = config.get('channel_id')
    if not channel_id:
        logger.error("Config is missing 'channel_id'", config=config_path)
        return
    channel_id = str(channel_id)
    messages = config.get('messages') or {}

    discord = DiscordChannel(bot_token)
    try:
        discord.validate(channel_id)
    except Exception as e:
        logger.error("Failed to authenticate with Discord",
                     error=str(e), error_type=type(e).__name__)
        return

    dispatcher = Dispatcher()
    mapper = Mapper(discord, channel_id, messages)
    dispatcher.set_default_handler(mapper.handle_osc_message)

    try:
        server = BlockingOSCUDPServer(("0.0.0.0", port), dispatcher)
        logger.info("OSC to Discord bridge running", port=port, channel_id=channel_id,
                    configured_addresses=list(mapper.messages))
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error("Server error occurred", error=str(e), error_type=type(e).__name__)


if __name__ == '__main__':
    main()
