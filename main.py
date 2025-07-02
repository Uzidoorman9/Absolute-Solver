import os
import random
import time
import asyncio
import functools
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from typing import Callable, Coroutine, Any

# -------- CONFIG & GLOBALS --------
intents = discord.Intents.all()  # Full intents for max features including members
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DISCORD_MANAGER_TOKEN = os.getenv("DISCORD_MANAGER_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TEST_GUILD_ID = 1388197138487574742
TEST_GUILD = discord.Object(id=TEST_GUILD_ID)

start_time = time.time()

# User data stores
user_balances = {}  # user_id -> oil drops (keep synced with user_data)
gambling_enabled = True
gambling_cooldowns = {}

talk_enabled_users = set()
length_limits = {}

# ----- NEW USER DATA for Murder Drones leveling system -----
# Structure: user_id -> { 'oil': int, 'xp': int, 'level': int, 'inventory': dict[item_name -> qty] }
user_data = {}

# Define Murder Drones themed roles by level
level_roles = [
    (0, "Worker Drone"),
    (5, "Disassembly Drone"),
    (10, "Electrician"),
    (15, "The Solver"),
    (20, "Uzi Doorman"),
    (25, "Murder Drone"),
]

OIL_GOD_ROLE_NAME = "Oil God"

# Shop items: name -> dict with price and xp gained on eating
shop_items = {
    "worker_drone_limb": {"price": 500, "xp": 5, "desc": "A severed Worker Drone limb."},
    "murder_drone_eye": {"price": 1500, "xp": 20, "desc": "A glowing eye from a Murder Drone."},
    "electrician_circuit": {"price": 1200, "xp": 15, "desc": "A spare circuit from Electrician."},
    "solver_brain_chip": {"price": 3000, "xp": 40, "desc": "A brain chip from The Solver."},
}

def xp_to_next_level(level: int) -> int:
    return 100 + level * 50

def get_user_data(user_id: int):
    if user_id not in user_data:
        # Initialize with 1000 oil by default
        user_data[user_id] = {
            "oil": 1000,
            "xp": 0,
            "level": 0,
            "inventory": {},
        }
    return user_data[user_id]

def update_oil_balance(user_id: int, amount: int):
    ud = get_user_data(user_id)
    ud["oil"] += amount
    if ud["oil"] < 0:
        ud["oil"] = 0
    user_balances[user_id] = ud["oil"]  # keep balances synced

async def update_roles(member: discord.Member):
    ud = get_user_data(member.id)
    level = ud["level"]

    # Determine highest role for current level
    role_name = None
    for lvl_req, name in reversed(level_roles):
        if level >= lvl_req:
            role_name = name
            break
    if role_name is None:
        role_name = level_roles[0][1]

    guild = member.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        role = await guild.create_role(name=role_name, reason="Level role auto-created")

    # Remove other Murder Drones roles
    roles_to_remove = [discord.utils.get(guild.roles, name=r[1]) for r in level_roles if discord.utils.get(guild.roles, name=r[1]) in member.roles]
    for r in roles_to_remove:
        if r != role:
            await member.remove_roles(r)

    if role not in member.roles:
        await member.add_roles(role)

async def update_oil_god_role(guild: discord.Guild):
    # Find top oil holder
    if not user_balances:
        return
    top_user_id = max(user_balances, key=lambda uid: user_balances.get(uid, 0))
    top_member = guild.get_member(top_user_id)
    if top_member is None:
        return

    role = discord.utils.get(guild.roles, name=OIL_GOD_ROLE_NAME)
    if role is None:
        role = await guild.create_role(name=OIL_GOD_ROLE_NAME, colour=discord.Colour.gold(), reason="Oil God role auto-created")

    # Remove Oil God from others
    for member in guild.members:
        if role in member.roles and member != top_member:
            await member.remove_roles(role)
    # Add to top member if not already
    if role not in top_member.roles:
        await top_member.add_roles(role)

# -------- EVENTS --------

@bot.event
async def on_ready():
    print(f"✅ Manager bot logged in as {bot.user}")
    await tree.sync(guild=TEST_GUILD)
    print(f"✅ Slash commands synced to guild {TEST_GUILD_ID}")

@bot.event
async def on_member_join(member: discord.Member):
    # Give Worker Drone role to everyone when they join
    guild = member.guild
    role = discord.utils.get(guild.roles, name="Worker Drone")
    if role is None:
        role = await guild.create_role(name="Worker Drone", reason="Worker Drone role auto-created")
    await member.add_roles(role)
    # Initialize user data
    get_user_data(member.id)
    update_oil_balance(member.id, 0)  # ensure sync with user_balances

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Talk mode repeats your messages & deletes yours
    if message.author.id in talk_enabled_users:
        await message.channel.send(message.content)
        try:
            await message.delete()
        except discord.Forbidden:
            pass
    # Length limits enforcement
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

# -------- UTILS --------

def get_balance(user_id: int) -> int:
    ud = get_user_data(user_id)
    return ud["oil"]

def check_cooldown(user_id: int, cd_seconds=5) -> bool:
    now = time.time()
    last = gambling_cooldowns.get(user_id, 0)
    return (now - last) > cd_seconds

def update_cooldown(user_id: int):
    gambling_cooldowns[user_id] = time.time()

def has_perms(interaction: discord.Interaction, perms: list[str]) -> bool:
    user_perms = interaction.user.guild_permissions
    return all(getattr(user_perms, perm, False) for perm in perms)

def ephemeral_send(interaction, content):
    return interaction.response.send_message(content, ephemeral=True)

def is_admin(interaction):
    return interaction.user.guild_permissions.administrator

def requires_perms(perms: list[str]):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not has_perms(interaction, perms):
                await ephemeral_send(interaction, f"❌ You need the following permissions: {', '.join(perms)}")
                return
            await func(interaction, *args, **kwargs)
        return wrapper
    return decorator

def gambling_command(func: Callable[[discord.Interaction, int], Coroutine[Any, Any, None]]):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, amount: int):
        if not gambling_enabled:
            await ephemeral_send(interaction, "❌ Gambling is currently disabled.")
            return
        if amount <= 0:
            await ephemeral_send(interaction, "❌ Amount must be positive.")
            return
        if get_balance(interaction.user.id) < amount:
            await ephemeral_send(interaction, "❌ You don't have enough oil drops.")
            return
        if not check_cooldown(interaction.user.id):
            await ephemeral_send(interaction, "⏳ Please wait before gambling again.")
            return
        update_cooldown(interaction.user.id)
        await func(interaction, amount)
    return wrapper

# -------- COMMANDS --------

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

@tree.command(name="clear", description="Delete messages (admin only)", guild=TEST_GUILD)
@app_commands.describe(amount="Number of messages to delete (1-100)")
@requires_perms(['manage_messages'])
async def clear(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 100:
        await ephemeral_send(interaction, "❌ Amount must be between 1 and 100.")
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)

@tree.command(name="kick", description="Kick a user", guild=TEST_GUILD)
@app_commands.describe(user="User to kick", reason="Reason for kick")
@requires_perms(['kick_members'])
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    try:
        await user.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {user} for: {reason or 'No reason provided'}")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to kick: {e}")

@tree.command(name="ban", description="Ban a user", guild=TEST_GUILD)
@app_commands.describe(user="User to ban", reason="Reason for ban")
@requires_perms(['ban_members'])
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    try:
        await user.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {user} for: {reason or 'No reason provided'}")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to ban: {e}")

@tree.command(name="unban", description="Unban a user by ID", guild=TEST_GUILD)
@app_commands.describe(user_id="User ID to unban")
@requires_perms(['ban_members'])
async def unban(interaction: discord.Interaction, user_id: int):
    banned_users = await interaction.guild.bans()
    user = discord.utils.find(lambda u: u.user.id == user_id, banned_users)
    if user is None:
        await ephemeral_send(interaction, "❌ User not found in ban list.")
        return
    try:
        await interaction.guild.unban(user.user)
        await interaction.response.send_message(f"✅ Unbanned {user.user}")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to unban: {e}")

@tree.command(name="mute", description="Timeout a user", guild=TEST_GUILD)
@app_commands.describe(user="User to timeout", duration="Duration in seconds")
@requires_perms(['moderate_members'])
async def mute(interaction: discord.Interaction, user: discord.Member, duration: int):
    try:
        await user.timeout(duration=duration)
        await interaction.response.send_message(f"🔇 Timed out {user} for {duration} seconds.")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to timeout: {e}")

@tree.command(name="unmute", description="Remove timeout", guild=TEST_GUILD)
@app_commands.describe(user="User to remove timeout from")
@requires_perms(['moderate_members'])
async def unmute(interaction: discord.Interaction, user: discord.Member):
    try:
        await user.timeout(None)
        await interaction.response.send_message(f"🔈 Removed timeout from {user}.")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to remove timeout: {e}")

@tree.command(name="roll", description="Roll a dice 1-100", guild=TEST_GUILD)
async def roll(interaction: discord.Interaction):
    result = random.randint(1, 100)
    await interaction.response.send_message(f"🎲 You rolled: {result}")

@tree.command(name="flip", description="Flip a coin", guild=TEST_GUILD)
async def flip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"🪙 The coin landed on: {result}")

@tree.command(name="8ball", description="Magic 8-ball answers", guild=TEST_GUILD)
@app_commands.describe(question="Your question")
async def eight_ball(interaction: discord.Interaction, question: str):
    responses = [
        "It is certain.", "Without a doubt.", "You may rely on it.", "Yes, definitely.",
        "Ask again later.", "Cannot predict now.", "Don't count on it.", "Very doubtful."
    ]
    answer = random.choice(responses)
    await interaction.response.send_message(f"🎱 Question: {question}\nAnswer: {answer}")

@tree.command(name="joke", description="Get a programming joke", guild=TEST_GUILD)
async def joke(interaction: discord.Interaction):
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs!",
        "There are 10 types of people in the world: those who understand binary, and those who don’t.",
        "Debugging: Being the detective in a crime movie where you are also the murderer.",
        "Why do Java developers wear glasses? Because they don't C#."
    ]
    await interaction.response.send_message(random.choice(jokes))

@tree.command(name="meme", description="Get a random meme image", guild=TEST_GUILD)
async def meme(interaction: discord.Interaction):
    memes = [
        "https://i.imgur.com/w3duR07.png",
        "https://i.imgur.com/2XjKxQy.jpeg",
        "https://i.imgur.com/mtL1U1X.jpg",
        "https://i.imgur.com/fnB6rH5.png"
    ]
    await interaction.response.send_message(random.choice(memes))

@tree.command(name="say", description="Make the bot say something", guild=TEST_GUILD)
@app_commands.describe(message="Message to say")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

@tree.command(name="toggle_talk", description="Toggle talk mode on/off (admin only)", guild=TEST_GUILD)
@requires_perms(['administrator'])
async def toggle_talk(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in talk_enabled_users:
        talk_enabled_users.remove(user_id)
        await interaction.response.send_message("Talk mode disabled.")
    else:
        talk_enabled_users.add(user_id)
        await interaction.response.send_message("Talk mode enabled.")

@tree.command(name="length_limit", description="Set message length limit and character (admin only)", guild=TEST_GUILD)
@requires_perms(['administrator'])
@app_commands.describe(max_len="Max length", character="Character to stay in")
async def length_limit(interaction: discord.Interaction, max_len: int, character: str):
    length_limits[interaction.guild.id] = {"max_len": max_len, "character": character}
    await interaction.response.send_message(f"Length limit set to {max_len} characters. Character set to {character}.")

@tree.command(name="remove_length_limit", description="Remove message length limit (admin only)", guild=TEST_GUILD)
@requires_perms(['administrator'])
async def remove_length_limit(interaction: discord.Interaction):
    if interaction.guild.id in length_limits:
        del length_limits[interaction.guild.id]
    await interaction.response.send_message("Message length limit removed.")

# --- Gambling ---

@tree.command(name="gamble", description="Gamble your oil drops", guild=TEST_GUILD)
@app_commands.describe(amount="Amount of oil to gamble")
@gambling_command
async def gamble(interaction: discord.Interaction, amount: int):
    user_id = interaction.user.id
    ud = get_user_data(user_id)
    # 50% chance to double or lose all
    if random.random() < 0.5:
        update_oil_balance(user_id, amount)  # win amount
        await interaction.response.send_message(f"🎉 You won {amount} oil drops!")
    else:
        update_oil_balance(user_id, -amount)  # lose amount
        await interaction.response.send_message(f"😢 You lost {amount} oil drops.")
    # Update Oil God role
    await update_oil_god_role(interaction.guild)

# --- Oil Balance and Inventory ---

@tree.command(name="balance", description="Check your oil drops balance", guild=TEST_GUILD)
async def balance(interaction: discord.Interaction):
    ud = get_user_data(interaction.user.id)
    await interaction.response.send_message(f"🛢️ You have {ud['oil']} oil drops.")

@tree.command(name="inventory", description="Show your inventory", guild=TEST_GUILD)
async def inventory(interaction: discord.Interaction):
    ud = get_user_data(interaction.user.id)
    inv = ud["inventory"]
    if not inv:
        await interaction.response.send_message("📦 Your inventory is empty.")
        return
    desc = "\n".join(f"{item}: {qty}" for item, qty in inv.items())
    await interaction.response.send_message(f"📦 Your inventory:\n{desc}")

@tree.command(name="buy", description="Buy an item from the shop", guild=TEST_GUILD)
@app_commands.describe(item="Item name to buy")
async def buy(interaction: discord.Interaction, item: str):
    item = item.lower()
    if item not in shop_items:
        await interaction.response.send_message(f"❌ Item '{item}' does not exist.")
        return
    ud = get_user_data(interaction.user.id)
    price = shop_items[item]["price"]
    if ud["oil"] < price:
        await interaction.response.send_message(f"❌ You need {price} oil drops to buy {item}.")
        return
    update_oil_balance(interaction.user.id, -price)
    inv = ud["inventory"]
    inv[item] = inv.get(item, 0) + 1
    await interaction.response.send_message(f"✅ Bought 1 {item} for {price} oil drops.")

@tree.command(name="eat", description="Eat an item to gain XP", guild=TEST_GUILD)
@app_commands.describe(item="Item name to eat")
async def eat(interaction: discord.Interaction, item: str):
    item = item.lower()
    ud = get_user_data(interaction.user.id)
    inv = ud["inventory"]
    if item not in inv or inv[item] == 0:
        await interaction.response.send_message(f"❌ You don't have any {item} to eat.")
        return
    # Consume 1 item
    inv[item] -= 1
    if inv[item] == 0:
        del inv[item]

    xp_gain = shop_items.get(item, {}).get("xp", 0)
    if xp_gain == 0:
        await interaction.response.send_message(f"❌ {item} cannot be eaten.")
        return
    ud["xp"] += xp_gain
    # Check level up
    leveled_up = False
    while ud["xp"] >= xp_to_next_level(ud["level"]):
        ud["xp"] -= xp_to_next_level(ud["level"])
        ud["level"] += 1
        leveled_up = True
    if leveled_up:
        await update_roles(interaction.user)
    await interaction.response.send_message(f"🍴 Ate 1 {item}, gained {xp_gain} XP. Level: {ud['level']} XP left: {ud['xp']}")

# --- Leaderboard for oil hoarders ---

@tree.command(name="leaderboard", description="Show top oil hoarders", guild=TEST_GUILD)
async def leaderboard(interaction: discord.Interaction):
    guild = interaction.guild
    # Sort by oil descending
    sorted_users = sorted(user_balances.items(), key=lambda x: x[1], reverse=True)
    lines = []
    count = 0
    for user_id, oil in sorted_users:
        if count >= 10:
            break
        member = guild.get_member(user_id)
        if member is None:
            continue
        lines.append(f"#{count+1} - {member.display_name}: {oil} oil drops")
        count += 1
    if not lines:
        await interaction.response.send_message("No data to display.")
        return
    await update_oil_god_role(guild)
    embed = discord.Embed(title="🛢️ Oil Hoarders Leaderboard", description="\n".join(lines), color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

# ------------- Run the bot -------------

bot.run(DISCORD_MANAGER_TOKEN)
