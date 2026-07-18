import discord
import fluxer
import logging

# General config:
DISCORD_CHANNEL_ID = 123
FLUXER_CHANNEL_ID  = 456
FLUXER_API_URL     = "https://api.fluxer.app/v1" # Changeme if self-hosting. :)

MAX_ATTACHMENTS   = 10
MAX_FILE_IN_BYTES = 10*1024*1024 # 10MB file limit for Discord for non-nitro. # TODO: Check if this is back down to 8??
MAX_TOTAL_BYTES   = 25*1024*1024 # 25MB Max size of all files attached to one message
DOWNLOAD_TIMEOUT  = 20           # Timeout for downlaoding an attachment
MESSAGE_LIMIT     = 2000         # Non-nitro message size, split into multiple.

# See .env.example. Copy to .env
load_dotenv()

DISCORD_BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
FLUXER_BOT_TOKEN    = os.getenv("FLUXER_BOT_TOKEN")
FLUXER_WEBHOOK_URL  = os.getenv("FLUXER_WEBHOOK_URL")


def main(): # public static void main (String args [])
    # Check if you've setup the .env correctly.
    fuckups = [
        name for name, value in (
            ("DISCORD_BOT_TOKEN",   DISCORD_BOT_TOKEN),
            ("DISCORD_WEBHOOK_URL", DISCORD_WEBHOOK_URL),
            ("FLUXER_BOT_TOKEN",    FLUXER_BOT_TOKEN),
            ("FLUXER_WEBHOOK_URL",  FLUXER_WEBHOOK_URL),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Oopsie poopsie, you forgot these value(s) in your .env: {", ".join(missing)}\n"
                          "Please check the .env.example and try again.")

    logging.basicConfig(
        level  = logging.INFO,
        format = "%(asctime)s %(levelname)s %(message)s"
    )

    try:
        # TODO: bridge()
        raise NotImplementedError
    except Exception as e:
        raise SystemError(f"Uh oh, little fucky wucky here: {e}")
