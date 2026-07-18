import discord
import fluxer
import logging
import asyncio
import os
from dotenv import load_dotenv

# General config shouldn't need to change these but here if Discord/Fluxer change limits:
MAX_ATTACHMENTS  = 10
MAX_FILE_BYTES   = 10*1024*1024 # 10MB file limit for Discord for non-nitro. # TODO: Check if this is back down to 8??
MAX_TOTAL_BYTES  = 25*1024*1024 # 25MB Max size of all files attached to one message
DOWNLOAD_TIMEOUT = 20           # Timeout for downlaoding an attachment
MESSAGE_LIMIT    = 2000         # Non-nitro message size, split into multiple.

# See .env.example. Copy to .env
load_dotenv()

DISCORD_BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
FLUXER_BOT_TOKEN    = os.getenv("FLUXER_BOT_TOKEN")
FLUXER_WEBHOOK_URL  = os.getenv("FLUXER_WEBHOOK_URL")
DISCORD_CHANNEL_ID  = os.getenv("DISCORD_CHANNEL_ID")
FLUXER_CHANNEL_ID   = os.getenv("FLUXER_CHANNEL_ID")
FLUXER_API_URL      = os.getenv("FLUXER_API_URL")

# Clients:
discord_intents = discord.Intents.none()
discord_intents.guilds = True
discord_intents.guild_messages = True
discord_intents.message_content = True
discord_client = discord.Client(intents=discord_intents)

fluxer_intents = (
    fluxer.Intents.GUILDS
    | fluxer.Intents.GUILD_MESSAGES
    | fluxer.Intents.MESSAGE_CONTENT
)
fluxer_client = fluxer.Client(intents=fluxer_intents, api_url=FLUXER_API_URL)

# Globals:
http_session              = None
discord_webhook           = None
fluxer_http               = None
fluxer_webhook_id         = None
fluxer_webhook_token      = None
discord_lock              = None
fluxer_lock               = None
fluxer_identity_overrides = True



@discord_client.event
async def on_ready():
    logging.info("Discord connected")

@fluxer_client.event
async def on_ready():
    logging.info("Fluxer connected")

@discord_client.event
async def on_message(message):
    # ignore other channels, bots, webhooks (inc. itself), etc.
    if (
        message.channel.id != int(DISCORD_CHANNEL_ID)
        or message.author.bot
        or message.webhook_id is not None
    ):
        return
    try:
        # lock so messages are same order see comment below in run_bridge
        async with fluxer_lock:
            logging.info("TODO discord message here")
    except Exception as error:
        # **DID YOU KNOW** HTTP errors can contain secret URLs?
        logging.error("Discord message %s failed (%s)", message.id, type(error).__name__)

@fluxer_client.event
async def on_message(message):
    # fluxer.py doesn't seem to expose webhook_id, so yipee? hope that's not needed in the future...
    if message.channel_id != int(FLUXER_CHANNEL_ID) or message.author.bot:
        return
    try:
        async with discord_lock:
            logging.info("TODO fluxer message here")
    except Exception as error:
        logging.error("Fluxer message %s failed (%s)", message.id, type(error).__name__)


async def run_bridge():
    global http_session
    global discord_webhook
    global fluxer_http
    global fluxer_webhook_id
    global fluxer_webhook_token
    global discord_lock
    global fluxer_lock

    # https://github.com/Fluxer-py/fluxer.py/blob/main/fluxer/models/webhook.py
    # fluxer needs the ID and URL seperate
    _, fluxer_webhook_id, fluxer_webhook_token = FLUXER_WEBHOOK_URL.rstrip("/").rsplit("/", 2)

    # setting
    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as http_session:
        discord_webhook = discord.Webhook.from_url(DISCORD_WEBHOOK_URL, session=http_session)

        fluxer_http = fluxer.HTTPClient(FLUXER_BOT_TOKEN, api_url=FLUXER_API_URL)

        # preserve message order. e.g., message 1 has an attachment, message 2 is just text 
        # then message 2 will appear before 1 without locks
        discord_lock = asyncio.Lock()
        fluxer_lock  = asyncio.Lock()

        discord_task = asyncio.create_task(discord_client.start(DISCORD_BOT_TOKEN))
        fluxer_task  = asyncio.create_task(fluxer_client.start(FLUXER_BOT_TOKEN))

        await asyncio.wait(
            {discord_task, fluxer_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        # gateway tassks should run until you quit or it crashes and burns. 
        # DEBUG: dob on the platform that stopped instead of silently crashing
        for name, task in (("Discord", discord_task), ("Fluxer", fluxer_task)):
            if task not in done:
                    continue
            error = task.exception()
            if error is not None:
                logging.error("%s gateway stopped (%s)", name, type(error).__name__) # fuckass __name__
                raise error
            raise RuntimeError(f"{name}'s gateway stopped")


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
        asyncio.run(run_bridge())
        raise NotImplementedError
    except Exception as e:
        raise SystemError(f"Uh oh, little fucky wucky here: {e}")
