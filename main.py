import os
import subprocess
import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import aiohttp
import asyncio
import functools
from typing import Callable, Coroutine, Any

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DISCORD_MANAGER_TOKEN = os.getenv("DISCORD_MANAGER_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

talk_enabled_users = set()
length_limits = {}

TEST_GUILD_ID = 1388197138487574742
TEST_GUILD = discord.Object(id=TEST_GUILD_ID)

start_time = time.time()

# --- Money system ---
user_balances = {}
gambling_enabled = True
gambling_cooldowns = {}

def get_balance(user_id: int) -> int:
    return user_balances.get(user_id, 1000)  # start users with 1000 oil drops

def update_balance(user_id: int, amount: int):
    user_balances[user_id] = get_balance(user_id) + amount

def check_cooldown(user_id: int) -> bool:
    now = time.time()
    if user_id not in gambling_cooldowns or now - gambling_cooldowns[user_id] > 5:
        return True
    return False

def update_cooldown(user_id: int):
    gambling_cooldowns[user_id] = time.time()

def gambling_command(func: Callable[[discord.Interaction, int], Coroutine[Any, Any, None]]):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, amount: int):
        if not gambling_enabled:
            await interaction.response.send_message("❌ Gambling commands are currently disabled.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
            return
        if get_balance(interaction.user.id) < amount:
            await interaction.response.send_message("❌ You don't have enough oil drops.", ephemeral=True)
            return
        if not check_cooldown(interaction.user.id):
            await interaction.response.send_message("⏳ Please wait before gambling again.", ephemeral=True)
            return
        update_cooldown(interaction.user.id)
        await func(interaction, amount)
    return wrapper

# ----------------------
# EVENTS
# ----------------------

@bot.event
async def on_ready():
    print(f"✅ Manager bot logged in as {bot.user}")
    await tree.sync(guild=TEST_GUILD)
    print(f"✅ Slash commands synced to guild {TEST_GUILD_ID}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Talk mode: repeat & delete
    if message.author.id in talk_enabled_users:
        await message.channel.send(message.content)
        try:
            await message.delete()
        except discord.Forbidden:
            pass

    # Length limit enforcement
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

# ----------------------
# BASIC COMMANDS
# ----------------------

@tree.command(name="ping", description="Check if bot is alive", guild=TEST_GUILD)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

@tree.command(name="uptime", description="Show how long the bot has been running", guild=TEST_GUILD)
async def uptime(interaction: discord.Interaction):
    elapsed = int(time.time() - start_time)
    hours, rem = divmod(elapsed, 3600)
    minutes, seconds = divmod(rem, 60)
    await interaction.response.send_message(f"⏳ Uptime: {hours}h {minutes}m {seconds}s")

@tree.command(name="invite", description="Get invite link for this bot", guild=TEST_GUILD)
async def invite(interaction: discord.Interaction):
    client_id = bot.user.id
    perms = 274877991936  # all permissions, adjust if you want
    invite_url = f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions={perms}&scope=bot%20applications.commands"
    await interaction.response.send_message(f"🔗 Invite me with: {invite_url}")

@tree.command(name="botinfo", description="Information about this bot", guild=TEST_GUILD)
async def botinfo(interaction: discord.Interaction):
    users = sum(g.member_count for g in bot.guilds)
    embed = discord.Embed(title="Bot Info", color=discord.Color.purple())
    embed.add_field(name="Name", value=bot.user.name)
    embed.add_field(name="ID", value=bot.user.id)
    embed.add_field(name="Servers", value=len(bot.guilds))
    embed.add_field(name="Users", value=users)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@tree.command(name="userinfo", description="Get info about a user", guild=TEST_GUILD)
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

@tree.command(name="serverinfo", description="Get info about the server", guild=TEST_GUILD)
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

@tree.command(name="avatar", description="Show a user's avatar", guild=TEST_GUILD)
@app_commands.describe(user="User to show avatar of")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user}'s Avatar")
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# ----------------------
# MODERATION COMMANDS
# ----------------------

@tree.command(name="clear", description="Delete messages in this channel (admin only)", guild=TEST_GUILD)
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

@tree.command(name="kick", description="Kick a user from the server", guild=TEST_GUILD)
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

@tree.command(name="ban", description="Ban a user from the server", guild=TEST_GUILD)
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

@tree.command(name="unban", description="Unban a user by ID", guild=TEST_GUILD)
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

@tree.command(name="mute", description="Timeout a user (mute)", guild=TEST_GUILD)
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

@tree.command(name="unmute", description="Remove timeout from a user", guild=TEST_GUILD)
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

# ----------------------
# FUN COMMANDS
# ----------------------

@tree.command(name="roll", description="Roll a dice (1-100)", guild=TEST_GUILD)
async def roll(interaction: discord.Interaction):
    result = random.randint(1, 100)
    await interaction.response.send_message(f"🎲 You rolled: {result}")

@tree.command(name="flip", description="Flip a coin", guild=TEST_GUILD)
async def flip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"🪙 The coin landed on: {result}")

@tree.command(name="8ball", description="Ask the magic 8-ball a question", guild=TEST_GUILD)
@app_commands.describe(question="Your question")
async def eight_ball(interaction: discord.Interaction, question: str):
    responses = [
        "It is certain.", "Without a doubt.", "You may rely on it.", "Yes, definitely.",
        "Ask again later.", "Cannot predict now.", "Don't count on it.", "Very doubtful."
    ]
    answer = random.choice(responses)
    await interaction.response.send_message(f"🎱 Question: {question}\nAnswer: {answer}")

@tree.command(name="joke", description="Get a random programming joke", guild=TEST_GUILD)
async def joke(interaction: discord.Interaction):
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs!",
        "There are 10 types of people in the world: those who understand binary, and those who don’t.",
        "Debugging: Being the detective in a crime movie where you are also the murderer.",
        "Why do Java developers wear glasses? Because they don't C#."
    ]
    await interaction.response.send_message(random.choice(jokes))

@tree.command(name="meme", description="Get a random meme", guild=TEST_GUILD)
async def meme(interaction: discord.Interaction):
    memes = [
        "https://i.imgur.com/w3duR07.png",
        "https://i.imgur.com/2XjKxQy.jpeg",
        "https://i.imgur.com/mtL1U1X.jpg",
        "https://i.imgur.com/fnB6rH5.png"
    ]
    await interaction.response.send_message(random.choice(memes))

@tree.command(name="say", description="Make the bot say something", guild=TEST_GUILD)
@app_commands.describe(message="What the bot should say")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    await interaction.delete_original_response()
    await interaction.channel.send(message)

@tree.command(name="cat", description="Get a random cat picture", guild=TEST_GUILD)
async def cat(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.thecatapi.com/v1/images/search") as resp:
            data = await resp.json()
            url = data[0]['url']
            await interaction.response.send_message(url)

@tree.command(name="dog", description="Get a random dog picture", guild=TEST_GUILD)
async def dog(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://dog.ceo/api/breeds/image/random") as resp:
            data = await resp.json()
            url = data['message']
            await interaction.response.send_message(url)

# ----------------------
# TALK MODE & LENGTH LIMITS
# ----------------------

@tree.command(name="talk_toggle", description="Toggle talk mode ON/OFF. Bot repeats your messages and deletes yours.", guild=TEST_GUILD)
async def talk_toggle(interaction: discord.Interaction):
    uid = interaction.user.id
    if uid in talk_enabled_users:
        talk_enabled_users.remove(uid)
        await interaction.response.send_message("🛑 Talk mode disabled.", ephemeral=True)
    else:
        talk_enabled_users.add(uid)
        await interaction.response.send_message("✅ Talk mode enabled.", ephemeral=True)

@tree.command(name="length", description="Set chat length limit and character name.", guild=TEST_GUILD)
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

# ----------------------
# GAMBLING COMMANDS
# ----------------------

@tree.command(name="balance", description="Check your oil drops balance", guild=TEST_GUILD)
async def balance(interaction: discord.Interaction):
    bal = get_balance(interaction.user.id)
    await interaction.response.send_message(f"🛢️ You have {bal} oil drops.")

@tree.command(name="give", description="Give oil drops to another user", guild=TEST_GUILD)
@app_commands.describe(user="User to give oil drops to", amount="Amount to give")
async def give(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
        return
    if get_balance(interaction.user.id) < amount:
        await interaction.response.send_message("❌ You don't have enough oil drops.", ephemeral=True)
        return
    update_balance(interaction.user.id, -amount)
    update_balance(user.id, amount)
    await interaction.response.send_message(f"✅ Gave {amount} oil drops to {user.mention}.")

@tree.command(name="gamble", description="Gamble your oil drops (win or lose)", guild=TEST_GUILD)
@gambling_command
async def gamble(interaction: discord.Interaction, amount: int):
    win = random.random() < 0.5
    if win:
        winnings = amount
        update_balance(interaction.user.id, winnings)
        await interaction.response.send_message(f"🎉 You won {winnings} oil drops! 🎉")
    else:
        update_balance(interaction.user.id, -amount)
        await interaction.response.send_message(f"😢 You lost {amount} oil drops. Better luck next time!")

@tree.command(name="slots", description="Play slots to win oil drops", guild=TEST_GUILD)
@gambling_command
async def slots(interaction: discord.Interaction, amount: int):
    symbols = ["🍒", "🍋", "🍊", "🍉", "7️⃣", "⭐"]
    result = [random.choice(symbols) for _ in range(3)]
    await interaction.response.defer()
    await asyncio.sleep(1)  # suspense
    if len(set(result)) == 1:
        winnings = amount * 5
        update_balance(interaction.user.id, winnings)
        await interaction.followup.send(f"🎰 {' '.join(result)}\nJackpot! You won {winnings} oil drops!")
    elif len(set(result)) == 2:
        winnings = amount * 2
        update_balance(interaction.user.id, winnings)
        await interaction.followup.send(f"🎰 {' '.join(result)}\nNice! You won {winnings} oil drops!")
    else:
        update_balance(interaction.user.id, -amount)
        await interaction.followup.send(f"🎰 {' '.join(result)}\nNo win, you lost {amount} oil drops.")

@tree.command(name="coinflip", description="Flip a coin and bet oil drops", guild=TEST_GUILD)
@app_commands.describe(amount="Amount to bet", choice="Heads or Tails")
async def coinflip(interaction: discord.Interaction, amount: int, choice: str):
    choice = choice.lower()
    if choice not in ["heads", "tails"]:
        await interaction.response.send_message("❌ Choice must be 'heads' or 'tails'.", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
        return
    if get_balance(interaction.user.id) < amount:
        await interaction.response.send_message("❌ You don't have enough oil drops.", ephemeral=True)
        return
    if not check_cooldown(interaction.user.id):
        await interaction.response.send_message("⏳ Please wait before gambling again.", ephemeral=True)
        return
    update_cooldown(interaction.user.id)

    flip_result = random.choice(["heads", "tails"])
    if flip_result == choice:
        winnings = amount
        update_balance(interaction.user.id, winnings)
        await interaction.response.send_message(f"🪙 The coin landed on **{flip_result.capitalize()}**. You won {winnings} oil drops!")
    else:
        update_balance(interaction.user.id, -amount)
        await interaction.response.send_message(f"🪙 The coin landed on **{flip_result.capitalize()}**. You lost {amount} oil drops.")

# ----------------------
# ADMIN TOGGLES
# ----------------------

@tree.command(name="toggle_gambling", description="Enable or disable gambling commands (admin only)", guild=TEST_GUILD)
async def toggle_gambling(interaction: discord.Interaction):
    global gambling_enabled
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need Administrator permission.", ephemeral=True)
        return
    gambling_enabled = not gambling_enabled
    status = "enabled" if gambling_enabled else "disabled"
    await interaction.response.send_message(f"🎲 Gambling commands are now {status}.")

# ----------------------
# MAIN STARTUP
# ----------------------

if __name__ == "__main__":
    if not DISCORD_MANAGER_TOKEN:
        print("Error: DISCORD_MANAGER_TOKEN environment variable not set.")
        exit(1)
    bot.run(DISCORD_MANAGER_TOKEN)
