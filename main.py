import os
import subprocess
import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import aiohttp
import hashlib
import base64
import datetime
import google.generativeai as genai
from urllib.parse import quote_plus

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DISCORD_MANAGER_TOKEN = os.getenv("DISCORD_MANAGER_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

talk_enabled_users = set()
length_limits = {}

start_time = time.time()

genai.configure(api_key=GEMINI_API_KEY)

@bot.event
async def on_ready():
    print(f"✅ Manager bot logged in as {bot.user}")
    for guild in bot.guilds:
        try:
            await tree.sync(guild=guild)
            print(f"✅ Synced slash commands to guild: {guild.name} ({guild.id})")
        except discord.errors.Forbidden:
            print(f"❌ Missing access to sync commands in: {guild.name} ({guild.id})")

# ---------------------- ADMIN ----------------------

@tree.command(name="reload", description="Reload all slash commands (admin only)")
async def reload(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    try:
        for guild in bot.guilds:
            await tree.sync(guild=guild)
        await interaction.response.send_message("✅ Commands reloaded for all guilds.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to reload: {e}", ephemeral=True)

# ---------------------- UTILITIES ----------------------

@tree.command(name="ping", description="Check if bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

@tree.command(name="uptime", description="Show how long the bot has been running")
async def uptime(interaction: discord.Interaction):
    elapsed = int(time.time() - start_time)
    hours, rem = divmod(elapsed, 3600)
    minutes, seconds = divmod(rem, 60)
    await interaction.response.send_message(f"⏳ Uptime: {hours}h {minutes}m {seconds}s")

@tree.command(name="invite", description="Get invite link for this bot")
async def invite(interaction: discord.Interaction):
    client_id = bot.user.id
    invite_url = f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=274877991936&scope=bot%20applications.commands"
    await interaction.response.send_message(f"🔗 Invite me with: {invite_url}")

@tree.command(name="botinfo", description="Information about this bot")
async def botinfo(interaction: discord.Interaction):
    users = sum(g.member_count for g in bot.guilds)
    embed = discord.Embed(title="Bot Info", color=discord.Color.purple())
    embed.add_field(name="Name", value=bot.user.name)
    embed.add_field(name="ID", value=bot.user.id)
    embed.add_field(name="Servers", value=len(bot.guilds))
    embed.add_field(name="Users", value=users)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@tree.command(name="userinfo", description="Get info about a user")
@app_commands.describe(user="User to look up")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"User Info - {user}", color=discord.Color.blue())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id)
    embed.add_field(name="Bot?", value=user.bot)
    embed.add_field(name="Top Role", value=user.top_role.name)
    embed.add_field(name="Joined Server", value=user.joined_at.strftime("%Y-%m-%d %H:%M:%S"))
    embed.add_field(name="Account Created", value=user.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    await interaction.response.send_message(embed=embed)

@tree.command(name="serverinfo", description="Get info about the server")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"Server Info - {guild.name}", color=discord.Color.green())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
    embed.add_field(name="ID", value=guild.id)
    embed.add_field(name="Owner", value=str(guild.owner))
    embed.add_field(name="Members", value=guild.member_count)
    embed.add_field(name="Channels", value=len(guild.channels))
    embed.add_field(name="Created At", value=guild.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    await interaction.response.send_message(embed=embed)

@tree.command(name="avatar", description="Show a user's avatar")
@app_commands.describe(user="User to show avatar of")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user}'s Avatar")
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# ---------------------- MODERATION ----------------------

@tree.command(name="clear", description="Delete messages in this channel (admin only)")
@app_commands.describe(amount="Number of messages to delete (1-100)")
async def clear(interaction: discord.Interaction, amount: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You need Manage Messages permission.", ephemeral=True)
        return
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)

@tree.command(name="kick", description="Kick a user from the server")
@app_commands.describe(user="User to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ You need Kick Members permission.", ephemeral=True)
        return
    try:
        await user.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {user} for: {reason or 'No reason provided'}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to kick: {e}", ephemeral=True)

@tree.command(name="ban", description="Ban a user from the server")
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ You need Ban Members permission.", ephemeral=True)
        return
    try:
        await user.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {user} for: {reason or 'No reason provided'}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to ban: {e}", ephemeral=True)

@tree.command(name="unban", description="Unban a user by ID")
@app_commands.describe(user_id="ID of user to unban")
async def unban(interaction: discord.Interaction, user_id: int):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ You need Ban Members permission.", ephemeral=True)
        return
    banned_users = await interaction.guild.bans()
    user = discord.utils.find(lambda u: u.user.id == user_id, banned_users)
    if user is None:
        await interaction.response.send_message("❌ User not found in ban list.", ephemeral=True)
        return
    try:
        await interaction.guild.unban(user.user)
        await interaction.response.send_message(f"✅ Unbanned {user.user}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to unban: {e}", ephemeral=True)

@tree.command(name="mute", description="Timeout a user (mute)")
@app_commands.describe(user="User to timeout", duration="Duration in seconds")
async def mute(interaction: discord.Interaction, user: discord.Member, duration: int):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ You need Moderate Members permission.", ephemeral=True)
        return
    try:
        await user.timeout(duration=duration)
        await interaction.response.send_message(f"🔇 Timed out {user} for {duration} seconds.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to timeout: {e}", ephemeral=True)

@tree.command(name="unmute", description="Remove timeout from a user")
@app_commands.describe(user="User to remove timeout from")
async def unmute(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ You need Moderate Members permission.", ephemeral=True)
        return
    try:
        await user.timeout(None)
        await interaction.response.send_message(f"🔈 Removed timeout from {user}.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to remove timeout: {e}", ephemeral=True)

# ---------------------- FUN COMMANDS ----------------------

@tree.command(name="roll", description="Roll a dice (1-100)")
async def roll(interaction: discord.Interaction):
    result = random.randint(1, 100)
    await interaction.response.send_message(f"🎲 You rolled: {result}")

@tree.command(name="flip", description="Flip a coin")
async def flip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"🪙 The coin landed on: {result}")

@tree.command(name="8ball", description="Ask the magic 8-ball a question")
@app_commands.describe(question="Your question")
async def eight_ball(interaction: discord.Interaction, question: str):
    responses = [
        "It is certain.", "Without a doubt.", "You may rely on it.", "Yes, definitely.",
        "Ask again later.", "Cannot predict now.", "Don't count on it.", "Very doubtful."
    ]
    answer = random.choice(responses)
    await interaction.response.send_message(f"🎱 Question: {question}\nAnswer: {answer}")

@tree.command(name="joke", description="Get a random programming joke")
async def joke(interaction: discord.Interaction):
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs!",
        "There are 10 types of people in the world: those who understand binary, and those who don’t.",
        "Debugging: Being the detective in a crime movie where you are also the murderer.",
        "Why do Java developers wear glasses? Because they don't C#."
    ]
    await interaction.response.send_message(random.choice(jokes))

@tree.command(name="meme", description="Get a random meme")
async def meme(interaction: discord.Interaction):
    memes = [
        "https://i.imgur.com/w3duR07.png",
        "https://i.imgur.com/2XjKxQy.jpeg",
        "https://i.imgur.com/mtL1U1X.jpg",
        "https://i.imgur.com/fnB6rH5.png"
    ]
    await interaction.response.send_message(random.choice(memes))

@tree.command(name="say", description="Make the bot say something")
@app_commands.describe(message="What the bot should say")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    await interaction.delete_original_response()
    await interaction.channel.send(message)

@tree.command(name="cat", description="Get a random cat picture")
async def cat(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.thecatapi.com/v1/images/search") as resp:
            data = await resp.json()
            url = data[0]['url']
            await interaction.response.send_message(url)

@tree.command(name="dog", description="Get a random dog picture")
async def dog(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://dog.ceo/api/breeds/image/random") as resp:
            data = await resp.json()
            url = data['message']
            await interaction.response.send_message(url)

# ---------------------- IMAGE GENERATION ----------------------

@tree.command(name="generate", description="Generate an image from a prompt")
@app_commands.describe(prompt="Describe the image you want")
async def generate(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        response = genai.generate_image(
            model="image-alpha-001",
            prompt=prompt,
            max_tokens=256,
            temperature=0.75,
            size="1024x1024",
        )
        image_url = response.data[0].image.url
        embed = discord.Embed(title="🖼️ Generated Image", description=prompt)
        embed.set_image(url=image_url)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to generate image: {e}")

# ---------------------- IMAGE ANALYSIS ----------------------

@tree.command(name="analyze", description="Analyze an image to get a description")
@app_commands.describe(image="Upload an image to analyze")
async def analyze(interaction: discord.Interaction, image: discord.Attachment):
    await interaction.response.defer()
    if not image.content_type or not image.content_type.startswith("image/"):
        await interaction.followup.send("❌ Please upload a valid image file.")
        return
    try:
        response = genai.chat.completions.create(
            model="gemini-multimodal-beta",
            modalities=["text", "image"],
            prompt=[
                {"type": "text", "text": "Describe the contents of this image."},
                {"type": "image_url", "image_url": {"url": image.url}},
            ],
            temperature=0.3,
            max_output_tokens=256,
        )
        desc = response.choices[0].message.content.strip()
        await interaction.followup.send(f"🖼️ Image analysis:\n{desc}")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to analyze image: {e}")

# ---------------------- REVERSE IMAGE SEARCH ----------------------

@tree.command(name="reverse", description="Get a reverse image search link")
@app_commands.describe(image="Upload an image to reverse search")
async def reverse_search(interaction: discord.Interaction, image: discord.Attachment):
    if not image.content_type or not image.content_type.startswith("image/"):
        await interaction.response.send_message("❌ Please upload a valid image file.", ephemeral=True)
        return
    search_url = f"https://www.google.com/searchbyimage?image_url={quote_plus(image.url)}"
    await interaction.response.send_message(f"🔍 Reverse Image Search: {search_url}")

# ---------------------- TALK MODE & LENGTH LIMITS ----------------------

@tree.command(name="talk_toggle", description="Toggle talk mode ON/OFF. Bot repeats your messages and deletes yours.")
async def talk_toggle(interaction: discord.Interaction):
    uid = interaction.user.id
    if uid in talk_enabled_users:
        talk_enabled_users.remove(uid)
        await interaction.response.send_message("🛑 Talk mode disabled.", ephemeral=True)
    else:
        talk_enabled_users.add(uid)
        await interaction.response.send_message("✅ Talk mode enabled.", ephemeral=True)

@tree.command(name="length", description="Set chat length limit and character name.")
@app_commands.describe(
    max_length="Max characters per message",
    character="Character name users should roleplay as"
)
async def set_length(interaction: discord.Interaction, max_length: int, character: str):
    if max_length <= 0:
        await interaction.response.send_message("❌ Max length must be positive.", ephemeral=True)
        return
    length_limits[interaction.guild_id] = {"max_len": max_length, "character": character}
    await interaction.response.send_message(
        f"✅ Chat length limit set to {max_length}. Users must roleplay as **{character}**."
    )

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.author.id in talk_enabled_users:
        await message.channel.send(message.content)
        try:
            await message.delete()
        except discord.Forbidden:
            pass

    guild_id = message.guild.id if message.guild else None
    if guild_id in length_limits:
        limit_info = length_limits[guild_id]
        max_len = limit_info["max_len"]
        character = limit_info["character"]
        if len(message.content) > max_len:
            await message.channel.send(
                f"⚠️ Your message is too long! Please keep it under {max_len} characters and stay in character as **{character}**."
            )
            try:
                await message.delete()
            except discord.Forbidden:
                pass

    await bot.process_commands(message)

# ---------------------- SPAWN CHILD BOT ----------------------

@tree.command(name="bot", description="Spawn a Gemini chatbot using another bot's token.")
@app_commands.describe(
    prompt="The personality or behavior prompt for the chatbot",
    token="The Discord token of the bot to turn into a chatbot"
)
async def spawn_bot(interaction: discord.Interaction, prompt: str, token: str):
    if not GEMINI_API_KEY:
        await interaction.response.send_message("❌ Gemini API key not set.", ephemeral=True)
        return
    await interaction.response.send_message("🚀 Starting chatbot...", ephemeral=True)
    subprocess.Popen([
        "python", "child_bot.py",
        prompt,
        GEMINI_API_KEY,
        token
    ])

bot.run(DISCORD_MANAGER_TOKEN)
