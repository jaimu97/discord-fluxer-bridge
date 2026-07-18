import discord
import fluxer
import logging
import asyncio
import aiohttp
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
    fluxer.Intents.GUILDS | fluxer.Intents.GUILD_MESSAGES | fluxer.Intents.MESSAGE_CONTENT
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


async def relay(message: discord.Message | fluxer.Message, from_fluxer : bool) -> None:
    global fluxer_identity_overrides
    
    # DEBUG:
    expected_type = fluxer.Message if from_fluxer else discord.Message
    direction = "Fluxer -> Discord" if from_fluxer else "Discord -> Fluxer"
    logging.debug("Relaying message %s (%s), content=%r", message.id, direction, message.content)
    # END DEBUG

    prepared = []
    notices  = []
    total    = 0

    for index, attachment in enumerate(message.attachments):
        # remove fucky chars from filenames and not too long
        name = re.sub(r"[^A-Za-z0-9._() -]+", "_", attachment.filename)[:180]

        if index >= MAX_ATTACHMENTS:
            notices.append(f"{name} exceeds the attachment count limit")
            continue
        if attachment.size > MAX_FILE_IN_BYTES or total + attachment.size > MAX_TOTAL_BYTES:
            notices.append(f"{name} exceeds the attachment size limit")
            continue

        try:
            if from_fluxer:
                # streaming is absolute cock and ball torture 
                # especially with missing/shit documentation (tl;dr stream it in 64k chunks)
                downloaded = []
                size       = 0

                async with http_session.get(attachment.url) as response:
                    response.raise_for_status()
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE_IN_BYTES:
                            raise ValueError("file too large")
                        downloaded.append(chunk)
                data = b"".join(downloaded)
            else: # from discord
                # https://discordpy-reborn.readthedocs.io/en/latest/api.html?highlight=attachment%20read#discord.Attachment.read
                data = await asyncio.wait_for(
                    attachment.read(), timeout=DOWNLOAD_TIMEOUT
                )

            # schizo moment: check the actual bytes in case source metadata was wrong.
            if len(data) > MAX_FILE_IN_BYTES or total + len(data) > MAX_TOTAL_BYTES:
                raise ValueError("file too large")
            prepared.append((name or "attachment", data))
            total += len(data)
        except Exception as error: # catch & report but continue so it doesn't just fuck everything
            logging.warning("Attachment %s omitted (%s)", name, type(error).__name__)
            notices.append(f"{name} could not be transferred")

    # FIXME?? I honestly have no fucking idea how to handle @ mentions unless users link their usernames
    # but for people who aren't using one or the other (why this bot exists) wtf do I do?
    # HACK: Insert a zero-width space into mention so it remains readable but can't notify users, 
    # roles, @here, or @everyone on the other side of the ether.
    # https://unicode-explorer.com/c/200B
    # e.g. "@​everyone" <- there's a zero width space in there (or should be)
    content = message.content or ""
    content = re.sub(r"<@([!&]?\d+)>",      "<@\u200b\\1>", content)
    content = re.sub(r"@(everyone|here)\b", "@\u200b\\1",   content, flags=re.IGNORECASE)
    # any other mention cases?? might be possible to keep role mentions if linked through the bots?

    # explain why attachments missing rather than giving bot flak for not working
    if notices:
        content += "\n" + "\n".join(
            f"[Attachment omitted: {notice}]" for notice in notices
        )

    # try split long text at a newline or space so it doesn't c
    # ut off messages
    content = content.strip()
    parts = []
    while len(content) > MESSAGE_LIMIT:
        cut = max(
            content.rfind("\n", 0, MESSAGE_LIMIT + 1),
            content.rfind(" ",  0, MESSAGE_LIMIT + 1),
        )
        if cut <= 0:
            cut = MESSAGE_LIMIT
            parts.append(content[:cut])
            content = content[cut:]
        else:
            parts.append(content[:cut])
            content = content[cut + 1 :]
    if content:
        parts.append(content)

    # picky webhooks reject payloads with neither content or files
    if not parts:
        parts = [""] if prepared else ["[No transferable content]"]

    # webhook username length limit = 80
    # (shoulddn't see "Unknown user" in client)
    username = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", message.author.display_name).split())[:80] or "Unknown user"

    if from_fluxer:
        # separate custom/default avatar properties w/fluxer.
        avatar = message.author.avatar_url or message.author.default_avatar_url
        for index, part in enumerate(parts):
            # TODO? is it better if attach files only to the first chunk of a split message or last?
            files = (
                [
                    discord.File(io.BytesIO(data), filename=name)
                    for name, data in prepared
                ]
                if index == 0
                else []
            )
            try:
                await discord_webhook.send(
                    content          = part,
                    username         = username,
                    avatar_url       = str(avatar) if avatar else None,
                    files            = files,
                    allowed_mentions = discord.AllowedMentions.none() # extra don't transfer pings
                )
            finally:
                for file in files:
                    file.close()
        logging.info("Relayed Fluxer message %s", message.id)
        return

    # Discord exposes one resolved display-avatar url
    avatar = str(message.author.display_avatar.url)
    for index, part in enumerate(parts):
        # files need to be dicts don't forget future me.
        files = (
            [fluxer.File(data, filename=name).to_dict() for name, data in prepared] if index == 0 else None
        )
        await fluxer_http.execute_webhook(
            fluxer_webhook_id,
            fluxer_webhook_token,
            content    = part or None,
            username   = username if fluxer_identity_overrides else None,
            avatar_url = avatar if fluxer_identity_overrides else None,
            files      = files,
            # TODO: is there some fluxer AllowedMentions.none?
        )
    logging.info("Relayed Discord message %s", message.id)


@discord_client.event
async def on_ready() -> None:
    logging.info("Discord connected")

@fluxer_client.event
async def on_ready() -> None:
    logging.info("Fluxer connected")

@discord_client.event
async def on_message(message: discord.Message) -> None:
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
            await relay(message, from_fluxer=False)
    except Exception as error:
        # **DID YOU KNOW** HTTP errors can contain secret URLs?
        logging.error("Discord message %s failed (%s)", message.id, type(error).__name__)

@fluxer_client.event
async def on_message(message: fluxer.Message) -> None:
    # fluxer.py doesn't seem to expose webhook_id, so yipee? hope that's not needed in the future...
    if message.channel_id != int(FLUXER_CHANNEL_ID) or message.author.bot:
        return
    try:
        async with discord_lock:
            await relay(message, from_fluxer=True)
    except Exception as error:
        logging.error("Fluxer message %s failed (%s)", message.id, type(error).__name__)


async def run_bridge() -> None:
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


def main() -> None: # public static void main (String args [])
    # Check if you've setup the .env correctly.
    fuckups = [
        name for name, value in (
            ("DISCORD_BOT_TOKEN",   DISCORD_BOT_TOKEN),
            ("DISCORD_WEBHOOK_URL", DISCORD_WEBHOOK_URL),
            ("FLUXER_BOT_TOKEN",    FLUXER_BOT_TOKEN),
            ("FLUXER_WEBHOOK_URL",  FLUXER_WEBHOOK_URL),
            ("DISCORD_CHANNEL_ID",  DISCORD_CHANNEL_ID),
            ("FLUXER_CHANNEL_ID",   FLUXER_CHANNEL_ID),
            ("FLUXER_API_URL",      FLUXER_API_URL)
        )
        if not value
    ]
    if fuckups:
        raise SystemExit(f"Oopsie poopsie, you forgot these value(s) in your .env: {", ".join(fuckups)}\n"
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


if __name__ == "__main__":
    main()
