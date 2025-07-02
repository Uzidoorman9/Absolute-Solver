import os
import random
import time
import asyncio
import functools
import discord
from discord.ext import commands
from discord import app_commands
from typing import Callable, Coroutine, Any

# -------- CONFIG & GLOBALS --------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DISCORD_MANAGER_TOKEN = os.getenv("DISCORD_MANAGER_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TEST_GUILD_ID = 1388197138487574742
TEST_GUILD = discord.Object(id=TEST_GUILD_ID)

start_time = time.time()

# User data stores
user_data = {}
gambling_enabled = True
gambling_cooldowns = {}

talk_enabled_users = set()
length_limits = {}

level_roles = [
    (0, "Worker Drone"),
    (5, "Disassembly Drone"),
    (10, "Electrician"),
    (15, "The Solver"),
    (20, "Uzi Doorman"),
    (25, "Murder Drone"),
]

OIL_GOD_ROLE_NAME = "Oil God"

# Shop items: item_key: price, xp gained, description
shop_items = {
    "worker_drone_arm": {"price": 500, "xp": 5, "desc": "A severed Worker Drone arm."},
    "worker_drone_leg": {"price": 750, "xp": 8, "desc": "A Worker Drone leg."},
    "disassembly_drone_limb": {"price": 1200, "xp": 12, "desc": "A limb from a Disassembly Drone."},
    "murder_drone_eye": {"price": 1500, "xp": 20, "desc": "A glowing eye from a Murder Drone."},
    "electrician_circuit": {"price": 1200, "xp": 15, "desc": "A spare circuit from Electrician."},
    "solver_brain_chip": {"price": 3000, "xp": 40, "desc": "A brain chip from The Solver."},
}

# -------- UTILITIES --------

def get_user_data(user_id: int):
    if user_id not in user_data:
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

def get_balance(user_id: int) -> int:
    ud = get_user_data(user_id)
    return ud["oil"]

def xp_to_next_level(level: int) -> int:
    return 100 + level * 50

async def update_roles(member: discord.Member):
    ud = get_user_data(member.id)
    level = ud["level"]
    role_name = None
    for lvl_req, name in reversed(level_roles):
        if level >= lvl_req:
            role_name = name
            break
    if role_name is None:
        role_name = level_roles[0][1]

    guild = member.guild
    new_role = discord.utils.get(guild.roles, name=role_name)
    if new_role is None:
        new_role = await guild.create_role(name=role_name, reason="Level role auto-created")

    # Remove all level roles except new_role
    roles_to_remove = [discord.utils.get(guild.roles, name=r[1]) for r in level_roles if discord.utils.get(guild.roles, name=r[1]) in member.roles and r[1] != role_name]
    for r in roles_to_remove:
        await member.remove_roles(r)

    # Add the new role if missing
    if new_role not in member.roles:
        await member.add_roles(new_role)

def try_level_up(user_id: int, member: discord.Member):
    ud = get_user_data(user_id)
    leveled_up = False
    while ud["xp"] >= xp_to_next_level(ud["level"]):
        ud["xp"] -= xp_to_next_level(ud["level"])
        ud["level"] += 1
        leveled_up = True
    if leveled_up:
        asyncio.create_task(update_roles(member))

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
            return await func(interaction, *args, **kwargs)
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

# -------- EVENTS --------

@bot.event
async def on_ready():
    print(f"✅ Manager bot logged in as {bot.user}")
    await tree.sync(guild=TEST_GUILD)
    print(f"✅ Slash commands synced to guild {TEST_GUILD_ID}")

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    role = discord.utils.get(guild.roles, name="Worker Drone")
    if role is None:
        role = await guild.create_role(name="Worker Drone", reason="Auto-created Worker Drone role")
    await member.add_roles(role)
    get_user_data(member.id)
    update_oil_balance(member.id, 0)

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

# -------- COMMANDS --------

# Basic commands

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
    perms = 274877991936
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
    ud = get_user_data(user.id)
    embed.add_field(name="Level", value=ud["level"])
    embed.add_field(name="XP", value=ud["xp"])
    embed.add_field(name="Oil Drops", value=ud["oil"])
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

# Moderation commands

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

# Fun commands

@tree.command(name="roll", description="Roll a dice 1-100", guild=TEST_GUILD)
async def roll(interaction: discord.Interaction):
    result = random.randint(1, 100)
    await interaction.response.send_message(f"🎲 You rolled: {result}")

@tree.command(name="coinflip", description="Flip a coin", guild=TEST_GUILD)
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"🪙 Coin flip result: {result}")

# Gambling commands

@tree.command(name="gamble", description="Gamble an amount of oil", guild=TEST_GUILD)
@app_commands.describe(amount="Amount of oil to gamble")
@gambling_command
async def gamble(interaction: discord.Interaction, amount: int):
    win = random.choice([True, False])
    if win:
        winnings = amount * 2
        update_oil_balance(interaction.user.id, winnings)
        await interaction.response.send_message(f"🎉 You won {winnings} oil drops!")
    else:
        update_oil_balance(interaction.user.id, -amount)
        await interaction.response.send_message(f"😢 You lost {amount} oil drops.")

@tree.command(name="balance", description="Check your oil balance", guild=TEST_GUILD)
@app_commands.describe(user="User to check")
async def balance(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    bal = get_balance(user.id)
    await interaction.response.send_message(f"💧 {user} has {bal} oil drops.")

# XP giving command

@tree.command(name="givexp", description="Give XP to a user (admin only)", guild=TEST_GUILD)
@app_commands.describe(user="User to give XP", amount="XP amount to give")
@requires_perms(['administrator'])
async def givexp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount <= 0:
        await ephemeral_send(interaction, "❌ Amount must be positive.")
        return
    ud = get_user_data(user.id)
    ud["xp"] += amount
    try_level_up(user.id, user)
    await interaction.response.send_message(f"✅ Given {amount} XP to {user.mention}. Current level: {ud['level']}.")

# Shop commands

@tree.command(name="shop", description="Show available items in the shop", guild=TEST_GUILD)
async def shop(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 Worker Drone Shop", color=discord.Color.blue())
    for key, item in shop_items.items():
        embed.add_field(name=key.replace("_", " ").title(), value=f"Price: {item['price']} oil | XP: {item['xp']}\n{item['desc']}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="buy", description="Buy an item from the shop", guild=TEST_GUILD)
@app_commands.describe(item_name="Name of the item to buy")
async def buy(interaction: discord.Interaction, item_name: str):
    item_key = item_name.lower().replace(" ", "_")
    if item_key not in shop_items:
        await ephemeral_send(interaction, f"❌ Item `{item_name}` not found in the shop.")
        return

    ud = get_user_data(interaction.user.id)
    item = shop_items[item_key]
    price = item["price"]
    xp_gain = item.get("xp", 0)

    if ud["oil"] < price:
        await ephemeral_send(interaction, "❌ You don't have enough oil to buy this item.")
        return

    ud["oil"] -= price
    inv = ud["inventory"]
    inv[item_key] = inv.get(item_key, 0) + 1

    ud["xp"] += xp_gain
    try_level_up(interaction.user.id, interaction.user)

    await interaction.response.send_message(f"✅ You bought 1 `{item_name}` for {price} oil and gained {xp_gain} XP! Current level: {ud['level']}.")

@tree.command(name="sell", description="Sell an item from your inventory", guild=TEST_GUILD)
@app_commands.describe(item_name="Name of the item to sell")
async def sell(interaction: discord.Interaction, item_name: str):
    item_key = item_name.lower().replace(" ", "_")
    ud = get_user_data(interaction.user.id)
    inv = ud["inventory"]
    if item_key not in inv or inv[item_key] <= 0:
        await ephemeral_send(interaction, f"❌ You don't have any `{item_name}` to sell.")
        return
    if item_key not in shop_items:
        await ephemeral_send(interaction, f"❌ `{item_name}` is not sellable.")
        return
    item = shop_items[item_key]
    sell_price = item["price"] // 2
    inv[item_key] -= 1
    if inv[item_key] == 0:
        del inv[item_key]
    ud["oil"] += sell_price
    await interaction.response.send_message(f"💰 Sold 1 `{item_name}` for {sell_price} oil drops.")

@tree.command(name="inventory", description="Show your inventory", guild=TEST_GUILD)
async def inventory(interaction: discord.Interaction):
    ud = get_user_data(interaction.user.id)
    inv = ud["inventory"]
    if not inv:
        await interaction.response.send_message("📦 Your inventory is empty.")
        return
    embed = discord.Embed(title=f"📦 {interaction.user.display_name}'s Inventory", color=discord.Color.gold())
    for item_key, qty in inv.items():
        embed.add_field(name=item_key.replace("_", " ").title(), value=f"Quantity: {qty}", inline=False)
    await interaction.response.send_message(embed=embed)

# Talk toggle command

@tree.command(name="talk", description="Toggle talk mode (bot repeats your messages)", guild=TEST_GUILD)
async def talk(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in talk_enabled_users:
        talk_enabled_users.remove(user_id)
        await interaction.response.send_message("🤖 Talk mode disabled.")
    else:
        talk_enabled_users.add(user_id)
        await interaction.response.send_message("🤖 Talk mode enabled. I will repeat your messages.")

# Length limit command

@tree.command(name="setlengthlimit", description="Set max message length and character for server", guild=TEST_GUILD)
@app_commands.describe(max_len="Max characters allowed", character="Roleplay character name")
@requires_perms(['manage_guild'])
async def setlengthlimit(interaction: discord.Interaction, max_len: int, character: str):
    if max_len <= 0:
        await ephemeral_send(interaction, "❌ Max length must be positive.")
        return
    length_limits[interaction.guild.id] = {"max_len": max_len, "character": character}
    await interaction.response.send_message(f"✅ Length limit set to {max_len} for character **{character}**.")

@tree.command(name="removelengthlimit", description="Remove length limit for server", guild=TEST_GUILD)
@requires_perms(['manage_guild'])
async def removelengthlimit(interaction: discord.Interaction):
    if interaction.guild.id in length_limits:
        del length_limits[interaction.guild.id]
        await interaction.response.send_message("✅ Length limit removed.")
    else:
        await ephemeral_send(interaction, "❌ No length limit set.")

# Leaderboard command

@tree.command(name="leaderboard", description="Show top users by oil drops", guild=TEST_GUILD)
async def leaderboard(interaction: discord.Interaction):
    if not user_data:
        await interaction.response.send_message("No users found.")
        return
    top_users = sorted(user_data.items(), key=lambda x: x[1]["oil"], reverse=True)[:10]
    embed = discord.Embed(title="💧 Oil Drops Leaderboard", color=discord.Color.teal())
    for i, (user_id, data) in enumerate(top_users, start=1):
        member = interaction.guild.get_member(user_id)
        name = member.display_name if member else f"User ID {user_id}"
        embed.add_field(name=f"{i}. {name}", value=f"{data['oil']} oil drops", inline=False)
    await interaction.response.send_message(embed=embed)

# Admin toggle gambling command

@tree.command(name="togglegambling", description="Toggle gambling enabled/disabled (admin only)", guild=TEST_GUILD)
@requires_perms(['administrator'])
async def togglegambling(interaction: discord.Interaction):
    global gambling_enabled
    gambling_enabled = not gambling_enabled
    state = "enabled" if gambling_enabled else "disabled"
    await interaction.response.send_message(f"🎲 Gambling has been {state}.")

# Reload commands - For example

@tree.command(name="reload", description="Reload commands (admin only)", guild=TEST_GUILD)
@requires_perms(['administrator'])
async def reload_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("🔄 Reloading commands...")
    try:
        await tree.sync(guild=TEST_GUILD)
        await interaction.followup.send("✅ Commands reloaded.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to reload commands: {e}")

# -------- RUN --------

bot.run(DISCORD_MANAGER_TOKEN)
