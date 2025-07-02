import os
import random
import time
import asyncio
import functools
import discord
from discord.ext import commands
from discord import app_commands
from typing import Callable, Coroutine, Any
from datetime import datetime, timedelta

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
            "blackjack": None,  # for blackjack game state
            "slots_cooldown": 0,
            "roulette_cooldown": 0,
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
    roles_to_remove = [
        discord.utils.get(guild.roles, name=r[1])
        for r in level_roles
        if discord.utils.get(guild.roles, name=r[1]) in member.roles and r[1] != role_name
    ]
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

def check_cooldown(user_id: int, cd_seconds=5, cd_name="default") -> bool:
    now = time.time()
    last = gambling_cooldowns.get((user_id, cd_name), 0)
    return (now - last) > cd_seconds

def update_cooldown(user_id: int, cd_name="default"):
    gambling_cooldowns[(user_id, cd_name)] = time.time()

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

def gambling_command(cd_name="default"):
    def decorator(func: Callable[[discord.Interaction, int], Coroutine[Any, Any, None]]):
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
            if not check_cooldown(interaction.user.id, 5, cd_name):
                await ephemeral_send(interaction, "⏳ Please wait before gambling again.")
                return
            update_cooldown(interaction.user.id, cd_name)
            await func(interaction, amount)
        return wrapper
    return decorator

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
    await update_roles(member)

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

# --- Existing commands from your fixed base ---
# ping
@tree.command(name="ping", description="Check if bot is alive", guild=TEST_GUILD)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

# uptime
@tree.command(name="uptime", description="Show how long the bot has been running", guild=TEST_GUILD)
async def uptime(interaction: discord.Interaction):
    elapsed = int(time.time() - start_time)
    hours, rem = divmod(elapsed, 3600)
    minutes, seconds = divmod(rem, 60)
    await interaction.response.send_message(f"⏳ Uptime: {hours}h {minutes}m {seconds}s")

# invite
@tree.command(name="invite", description="Get invite link for this bot", guild=TEST_GUILD)
async def invite(interaction: discord.Interaction):
    client_id = bot.user.id
    perms = 274877991936
    invite_url = f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions={perms}&scope=bot%20applications.commands"
    await interaction.response.send_message(f"🔗 Invite me with: {invite_url}")

# botinfo
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

# userinfo
@tree.command(name="userinfo", description="Get info about a user", guild=TEST_GUILD)
@app_commands.describe(user="User to look up")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"User Info - {user}", color=discord.Color.blue())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id)
    embed.add_field(name="Bot?", value=user.bot)
    embed.add_field(name="Top Role", value=user.top_role.name)
    embed.add_field(name="Joined Server", value=user.joined_at.strftime("%Y-%m-%d %H:%M:%S") if user.joined_at else "N/A")
    embed.add_field(name="Account Created", value=user.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    ud = get_user_data(user.id)
    embed.add_field(name="Level", value=ud["level"])
    embed.add_field(name="XP", value=ud["xp"])
    embed.add_field(name="Oil Drops", value=ud["oil"])
    await interaction.response.send_message(embed=embed)

# serverinfo
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

# avatar
@tree.command(name="avatar", description="Show a user's avatar", guild=TEST_GUILD)
@app_commands.describe(user="User to show avatar of")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user}'s Avatar")
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# clear
@tree.command(name="clear", description="Delete messages (admin only)", guild=TEST_GUILD)
@app_commands.describe(amount="Number of messages to delete (1-100)")
@requires_perms(['manage_messages'])
async def clear(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 100:
        await ephemeral_send(interaction, "❌ Amount must be between 1 and 100.")
        return
    if not isinstance(interaction.channel, discord.TextChannel):
        await ephemeral_send(interaction, "❌ This command can only be used in text channels.")
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)

# kick
@tree.command(name="kick", description="Kick a user", guild=TEST_GUILD)
@app_commands.describe(user="User to kick", reason="Reason for kick")
@requires_perms(['kick_members'])
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    try:
        await user.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {user} for: {reason or 'No reason provided'}")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to kick: {e}")

# ban
@tree.command(name="ban", description="Ban a user", guild=TEST_GUILD)
@app_commands.describe(user="User to ban", reason="Reason for ban")
@requires_perms(['ban_members'])
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    try:
        await user.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {user} for: {reason or 'No reason provided'}")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to ban: {e}")

# unban
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

# mute (timeout)
@tree.command(name="mute", description="Timeout a user", guild=TEST_GUILD)
@app_commands.describe(user="User to timeout", duration="Duration in seconds")
@requires_perms(['moderate_members'])
async def mute(interaction: discord.Interaction, user: discord.Member, duration: int):
    try:
        until = datetime.utcnow() + timedelta(seconds=duration)
        await user.timeout(until=until)
        await interaction.response.send_message(f"🔇 Timed out {user} for {duration} seconds.")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to timeout: {e}")

# unmute (remove timeout)
@tree.command(name="unmute", description="Remove timeout", guild=TEST_GUILD)
@app_commands.describe(user="User to remove timeout from")
@requires_perms(['moderate_members'])
async def unmute(interaction: discord.Interaction, user: discord.Member):
    try:
        await user.timeout(until=None)
        await interaction.response.send_message(f"🔈 Removed timeout from {user}.")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to remove timeout: {e}")

# roll dice
@tree.command(name="roll", description="Roll a dice 1-100", guild=TEST_GUILD)
async def roll(interaction: discord.Interaction):
    result = random.randint(1, 100)
    await interaction.response.send_message(f"🎲 You rolled: {result}")

# coinflip
@tree.command(name="coinflip", description="Flip a coin", guild=TEST_GUILD)
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"🪙 Coin flip result: {result}")

# gamble command decorator already defined

# gamble
@tree.command(name="gamble", description="Gamble an amount of oil", guild=TEST_GUILD)
@app_commands.describe(amount="Amount of oil drops to gamble")
@gambling_command("gamble")
async def gamble(interaction: discord.Interaction, amount: int):
    win = random.choice([True, False])
    ud = get_user_data(interaction.user.id)
    if win:
        gain = amount
        update_oil_balance(interaction.user.id, gain)
        await interaction.response.send_message(f"🎉 You won {gain} oil drops!")
    else:
        loss = amount
        update_oil_balance(interaction.user.id, -loss)
        await interaction.response.send_message(f"💥 You lost {loss} oil drops!")

# slots
@tree.command(name="slots", description="Play the slot machine", guild=TEST_GUILD)
@app_commands.describe(amount="Bet amount")
@gambling_command("slots")
async def slots(interaction: discord.Interaction, amount: int):
    symbols = ["🍒", "🍋", "🍊", "🍉", "⭐", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    ud = get_user_data(interaction.user.id)
    payout = 0
    if result.count(result[0]) == 3:
        payout = amount * 5
    elif len(set(result)) == 2:
        payout = amount * 2
    else:
        payout = -amount
    update_oil_balance(interaction.user.id, payout)
    embed = discord.Embed(title="Slots Machine", description=" | ".join(result))
    if payout > 0:
        embed.add_field(name="Result", value=f"🎉 You won {payout} oil drops!")
    else:
        embed.add_field(name="Result", value=f"💥 You lost {amount} oil drops!")
    await interaction.response.send_message(embed=embed)

# blackjack (simplified version)
class BlackjackGame:
    def __init__(self, user_id):
        self.user_id = user_id
        self.deck = [str(i) for i in range(2, 11)] + ["J", "Q", "K", "A"] * 4
        random.shuffle(self.deck)
        self.player_hand = []
        self.dealer_hand = []
        self.finished = False

    def deal_card(self):
        return self.deck.pop()

    def hand_value(self, hand):
        value = 0
        aces = 0
        for card in hand:
            if card.isdigit():
                value += int(card)
            elif card in ["J", "Q", "K"]:
                value += 10
            else:  # Ace
                aces += 1
        for _ in range(aces):
            if value + 11 <= 21:
                value += 11
            else:
                value += 1
        return value

blackjack_games = {}

@tree.command(name="blackjack", description="Start a blackjack game", guild=TEST_GUILD)
@app_commands.describe(bet="Bet amount")
@gambling_command("blackjack")
async def blackjack(interaction: discord.Interaction, bet: int):
    if interaction.user.id in blackjack_games:
        await ephemeral_send(interaction, "❌ You already have an active blackjack game.")
        return
    ud = get_user_data(interaction.user.id)
    if bet > ud["oil"]:
        await ephemeral_send(interaction, "❌ You don't have enough oil drops.")
        return
    game = BlackjackGame(interaction.user.id)
    blackjack_games[interaction.user.id] = {"game": game, "bet": bet}
    # Deal initial cards
    game.player_hand.append(game.deal_card())
    game.player_hand.append(game.deal_card())
    game.dealer_hand.append(game.deal_card())
    game.dealer_hand.append(game.deal_card())
    await interaction.response.send_message(
        f"🃏 Blackjack started!\nYour hand: {game.player_hand} (Value: {game.hand_value(game.player_hand)})\n"
        f"Dealer's visible card: {game.dealer_hand[0]}\nUse /hit or /stand to continue."
    )

@tree.command(name="hit", description="Draw a card in blackjack", guild=TEST_GUILD)
async def hit(interaction: discord.Interaction):
    if interaction.user.id not in blackjack_games:
        await ephemeral_send(interaction, "❌ You have no active blackjack game.")
        return
    game = blackjack_games[interaction.user.id]["game"]
    bet = blackjack_games[interaction.user.id]["bet"]
    card = game.deal_card()
    game.player_hand.append(card)
    val = game.hand_value(game.player_hand)
    if val > 21:
        update_oil_balance(interaction.user.id, -bet)
        del blackjack_games[interaction.user.id]
        await interaction.response.send_message(f"🃏 You drew {card}. Your hand value is {val}. You busted and lost {bet} oil drops.")
    else:
        await interaction.response.send_message(f"🃏 You drew {card}. Your hand: {game.player_hand} (Value: {val})")

@tree.command(name="stand", description="Stand in blackjack", guild=TEST_GUILD)
async def stand(interaction: discord.Interaction):
    if interaction.user.id not in blackjack_games:
        await ephemeral_send(interaction, "❌ You have no active blackjack game.")
        return
    game = blackjack_games[interaction.user.id]["game"]
    bet = blackjack_games[interaction.user.id]["bet"]
    player_val = game.hand_value(game.player_hand)
    dealer_val = game.hand_value(game.dealer_hand)
    while dealer_val < 17:
        game.dealer_hand.append(game.deal_card())
        dealer_val = game.hand_value(game.dealer_hand)
    if dealer_val > 21 or player_val > dealer_val:
        update_oil_balance(interaction.user.id, bet)
        result = "won"
    elif player_val == dealer_val:
        result = "tied"
    else:
        update_oil_balance(interaction.user.id, -bet)
        result = "lost"
    del blackjack_games[interaction.user.id]
    await interaction.response.send_message(
        f"Dealer's hand: {game.dealer_hand} (Value: {dealer_val})\n"
        f"Your hand: {game.player_hand} (Value: {player_val})\nYou {result} the blackjack game."
    )

# trivia questions (small sample)
trivia_questions = [
    {"q": "What is the capital of France?", "a": "paris"},
    {"q": "Who painted the Mona Lisa?", "a": "da vinci"},
    {"q": "What year did the Titanic sink?", "a": "1912"},
]

active_trivia = {}

@tree.command(name="trivia", description="Start a trivia question", guild=TEST_GUILD)
async def trivia(interaction: discord.Interaction):
    if interaction.user.id in active_trivia:
        await ephemeral_send(interaction, "❌ You already have an active trivia question.")
        return
    question = random.choice(trivia_questions)
    active_trivia[interaction.user.id] = question
    await interaction.response.send_message(f"❓ Trivia: {question['q']} Reply with /answer command.")

@tree.command(name="answer", description="Answer the trivia question", guild=TEST_GUILD)
@app_commands.describe(answer="Your answer")
async def answer(interaction: discord.Interaction, answer: str):
    if interaction.user.id not in active_trivia:
        await ephemeral_send(interaction, "❌ You have no active trivia question.")
        return
    question = active_trivia[interaction.user.id]
    if answer.lower().strip() == question["a"]:
        ud = get_user_data(interaction.user.id)
        ud["xp"] += 10
        del active_trivia[interaction.user.id]
        await interaction.response.send_message("✅ Correct! You gained 10 XP.")
    else:
        await interaction.response.send_message("❌ Incorrect answer. Try again!")

# compliment
compliments = [
    "You're amazing!",
    "You're a star!",
    "You brighten up the day!",
    "You're a genius!",
    "You're unstoppable!",
]

@tree.command(name="compliment", description="Give a compliment", guild=TEST_GUILD)
async def compliment(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(compliments))

# insult
insults = [
    "You're as bright as a black hole.",
    "You have something on your chin... no, the third one down.",
    "You're the reason the gene pool needs a lifeguard.",
    "You bring everyone so much joy... when you leave the room.",
]

@tree.command(name="insult", description="Give a funny insult", guild=TEST_GUILD)
async def insult(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(insults))

# tell joke
jokes = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "I told my computer I needed a break, and it said 'No problem, I'll go to sleep.'",
    "Why did the scarecrow win an award? Because he was outstanding in his field!",
]

@tree.command(name="joke", description="Tell a joke", guild=TEST_GUILD)
async def joke(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(jokes))

# oil balance
@tree.command(name="balance", description="Check your oil drops balance", guild=TEST_GUILD)
async def balance(interaction: discord.Interaction):
    ud = get_user_data(interaction.user.id)
    await interaction.response.send_message(f"💰 You have {ud['oil']} oil drops.")

# give oil (admin)
@tree.command(name="giveoil", description="Give oil drops to a user", guild=TEST_GUILD)
@app_commands.describe(user="User to give oil to", amount="Amount to give")
@requires_perms(['administrator'])
async def giveoil(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount <= 0:
        await ephemeral_send(interaction, "❌ Amount must be positive.")
        return
    ud = get_user_data(user.id)
    ud["oil"] += amount
    await interaction.response.send_message(f"✅ Gave {amount} oil drops to {user}.")

# take oil (admin)
@tree.command(name="takeoil", description="Take oil drops from a user", guild=TEST_GUILD)
@app_commands.describe(user="User to take oil from", amount="Amount to take")
@requires_perms(['administrator'])
async def takeoil(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount <= 0:
        await ephemeral_send(interaction, "❌ Amount must be positive.")
        return
    ud = get_user_data(user.id)
    ud["oil"] = max(0, ud["oil"] - amount)
    await interaction.response.send_message(f"✅ Took {amount} oil drops from {user}.")

# XP give (admin)
@tree.command(name="givexp", description="Give XP to a user", guild=TEST_GUILD)
@app_commands.describe(user="User to give XP to", amount="Amount of XP")
@requires_perms(['administrator'])
async def givexp(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount <= 0:
        await ephemeral_send(interaction, "❌ Amount must be positive.")
        return
    ud = get_user_data(user.id)
    ud["xp"] += amount
    try_level_up(user.id, user)
    await interaction.response.send_message(f"✅ Gave {amount} XP to {user}.")

# XP leaderboard
@tree.command(name="xpleaderboard", description="Show top XP holders", guild=TEST_GUILD)
async def xpleaderboard(interaction: discord.Interaction):
    sorted_users = sorted(user_data.items(), key=lambda kv: kv[1]["xp"], reverse=True)[:10]
    embed = discord.Embed(title="XP Leaderboard", color=discord.Color.gold())
    for i, (user_id, data) in enumerate(sorted_users, 1):
        user = bot.get_user(user_id)
        user_display = user.name if user else f"User ID {user_id}"
        embed.add_field(name=f"#{i} - {user_display}", value=f"{data['xp']} XP", inline=False)
    await interaction.response.send_message(embed=embed)

# oil leaderboard
@tree.command(name="leaderboard", description="Show the top oil holders", guild=TEST_GUILD)
async def leaderboard(interaction: discord.Interaction):
    sorted_users = sorted(user_data.items(), key=lambda kv: kv[1]["oil"], reverse=True)[:10]
    embed = discord.Embed(title="Oil Drops Leaderboard", color=discord.Color.orange())
    for i, (user_id, data) in enumerate(sorted_users, 1):
        user = bot.get_user(user_id)
        user_display = user.name if user else f"User ID {user_id}"
        embed.add_field(name=f"#{i} - {user_display}", value=f"{data['oil']} oil drops", inline=False)
    await interaction.response.send_message(embed=embed)

# shop (your existing shop command, included here)

@tree.command(name="shop", description="Show the item shop", guild=TEST_GUILD)
async def shop(interaction: discord.Interaction):
    embed = discord.Embed(title="Item Shop", description="Items available for purchase", color=discord.Color.gold())
    for item_key, item in shop_items.items():
        embed.add_field(name=f"{item_key} - {item['price']} oil drops", value=item["desc"], inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="buy", description="Buy an item from the shop", guild=TEST_GUILD)
@app_commands.describe(item_key="Item to buy")
async def buy(interaction: discord.Interaction, item_key: str):
    item = shop_items.get(item_key)
    if not item:
        await ephemeral_send(interaction, "❌ Item not found.")
        return
    ud = get_user_data(interaction.user.id)
    if ud["oil"] < item["price"]:
        await ephemeral_send(interaction, "❌ You don't have enough oil drops to buy this item.")
        return
    ud["oil"] -= item["price"]
    ud["xp"] += item["xp"]
    inventory = ud["inventory"]
    inventory[item_key] = inventory.get(item_key, 0) + 1
    try_level_up(interaction.user.id, interaction.user)
    await interaction.response.send_message(f"✅ Bought {item_key}. You gained {item['xp']} XP.")

@tree.command(name="inventory", description="Show your inventory", guild=TEST_GUILD)
async def inventory(interaction: discord.Interaction):
    ud = get_user_data(interaction.user.id)
    inv = ud.get("inventory", {})
    if not inv:
        await interaction.response.send_message("🛒 Your inventory is empty.")
        return
    embed = discord.Embed(title=f"{interaction.user}'s Inventory", color=discord.Color.blurple())
    for item_key, count in inv.items():
        embed.add_field(name=item_key, value=f"Quantity: {count}", inline=False)
    await interaction.response.send_message(embed=embed)

# talk toggle commands

@tree.command(name="talk", description="Toggle talk mode", guild=TEST_GUILD)
async def talk(interaction: discord.Interaction):
    if interaction.user.id in talk_enabled_users:
        talk_enabled_users.remove(interaction.user.id)
        await interaction.response.send_message("🗣️ Talk mode disabled.")
    else:
        talk_enabled_users.add(interaction.user.id)
        await interaction.response.send_message("🗣️ Talk mode enabled.")

# Length limit commands

@tree.command(name="setlengthlimit", description="Set max message length for the server", guild=TEST_GUILD)
@requires_perms(['administrator'])
@app_commands.describe(max_length="Maximum message length", character="Character to stay in")
async def setlengthlimit(interaction: discord.Interaction, max_length: int, character: str):
    if max_length < 1:
        await ephemeral_send(interaction, "❌ Max length must be positive.")
        return
    length_limits[interaction.guild.id] = {"max_len": max_length, "character": character}
    await interaction.response.send_message(f"✅ Length limit set to {max_length} characters with character '{character}'.")

@tree.command(name="clearlengthlimit", description="Clear message length limit for the server", guild=TEST_GUILD)
@requires_perms(['administrator'])
async def clearlengthlimit(interaction: discord.Interaction):
    if interaction.guild.id in length_limits:
        del length_limits[interaction.guild.id]
        await interaction.response.send_message("✅ Length limit cleared.")
    else:
        await ephemeral_send(interaction, "❌ No length limit set.")

# Admin toggle gambling

@tree.command(name="togglegambling", description="Enable or disable gambling", guild=TEST_GUILD)
@requires_perms(['administrator'])
async def togglegambling(interaction: discord.Interaction):
    global gambling_enabled
    gambling_enabled = not gambling_enabled
    await interaction.response.send_message(f"Gambling enabled: {gambling_enabled}")

# Reload commands

@tree.command(name="reload", description="Reload slash commands", guild=TEST_GUILD)
@requires_perms(['administrator'])
async def reload_commands(interaction: discord.Interaction):
    await tree.sync(guild=TEST_GUILD)
    await interaction.response.send_message("🔄 Slash commands reloaded.")

# --- Extra commands start here: (more fun, utility, moderation, gambling, and economy) ---

# -------------- FUN COMMANDS --------------

@tree.command(name="say", description="Bot repeats your message", guild=TEST_GUILD)
@app_commands.describe(message="Message to say")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

@tree.command(name="reverse", description="Reverse your message", guild=TEST_GUILD)
@app_commands.describe(message="Message to reverse")
async def reverse(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message[::-1])

@tree.command(name="8ball", description="Ask the magic 8ball a question", guild=TEST_GUILD)
@app_commands.describe(question="Your question")
async def eight_ball(interaction: discord.Interaction, question: str):
    responses = [
        "It is certain.", "Without a doubt.", "You may rely on it.",
        "Ask again later.", "Better not tell you now.",
        "Don't count on it.", "My reply is no.", "Very doubtful."
    ]
    await interaction.response.send_message(f"🎱 Question: {question}\nAnswer: {random.choice(responses)}")

@tree.command(name="randomnumber", description="Generate a random number", guild=TEST_GUILD)
@app_commands.describe(minimum="Minimum number", maximum="Maximum number")
async def randomnumber(interaction: discord.Interaction, minimum: int = 0, maximum: int = 100):
    if minimum > maximum:
        await ephemeral_send(interaction, "❌ Minimum must be less than or equal to maximum.")
        return
    number = random.randint(minimum, maximum)
    await interaction.response.send_message(f"🎲 Your random number: {number}")

@tree.command(name="fact", description="Get a random fact", guild=TEST_GUILD)
async def fact(interaction: discord.Interaction):
    facts = [
        "Honey never spoils.",
        "Octopuses have three hearts.",
        "Bananas are berries.",
        "The Eiffel Tower can be 15 cm taller during hot days.",
        "Some cats are allergic to humans."
    ]
    await interaction.response.send_message(random.choice(facts))

@tree.command(name="rollstats", description="Roll stats for RPG characters", guild=TEST_GUILD)
async def rollstats(interaction: discord.Interaction):
    stats = [sum(sorted([random.randint(1,6) for _ in range(4)])[1:]) for _ in range(6)]
    await interaction.response.send_message(f"🎲 Your stats: {stats}")

# -------------- MODERATION COMMANDS --------------

@tree.command(name="warn", description="Warn a user", guild=TEST_GUILD)
@app_commands.describe(user="User to warn", reason="Reason for warning")
@requires_perms(['manage_messages'])
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    # This is a placeholder, you'd store warnings in a database or dict
    await interaction.response.send_message(f"⚠️ {user} has been warned for: {reason}")

@tree.command(name="masskick", description="Kick multiple users (admin only)", guild=TEST_GUILD)
@app_commands.describe(users="Users to kick (mention or ID separated by spaces)", reason="Reason for kick")
@requires_perms(['kick_members'])
async def masskick(interaction: discord.Interaction, users: str, reason: str = None):
    user_ids = [int(u.strip("<@!>")) for u in users.split()]
    kicked = []
    failed = []
    for uid in user_ids:
        member = interaction.guild.get_member(uid)
        if member:
            try:
                await member.kick(reason=reason)
                kicked.append(str(member))
            except:
                failed.append(str(member))
    await interaction.response.send_message(f"Kicked: {', '.join(kicked)}\nFailed: {', '.join(failed)}")

# -------------- UTILITY COMMANDS --------------

@tree.command(name="remindme", description="Set a reminder", guild=TEST_GUILD)
@app_commands.describe(seconds="Seconds to wait", message="Reminder message")
async def remindme(interaction: discord.Interaction, seconds: int, message: str):
    await interaction.response.send_message(f"⏰ Reminder set for {seconds} seconds from now.")
    await asyncio.sleep(seconds)
    try:
        await interaction.user.send(f"⏰ Reminder: {message}")
    except:
        pass

@tree.command(name="pingall", description="Ping everyone in the server (admin only)", guild=TEST_GUILD)
@requires_perms(['administrator'])
async def pingall(interaction: discord.Interaction):
    await interaction.response.send_message("@everyone", allowed_mentions=discord.AllowedMentions(everyone=True))

# -------------- RANDOM GENERATORS --------------

@tree.command(name="randomcolor", description="Generate a random color", guild=TEST_GUILD)
async def randomcolor(interaction: discord.Interaction):
    color = discord.Color(random.randint(0, 0xFFFFFF))
    await interaction.response.send_message(f"🎨 Random color: {color} (#{color.value:06X})")

@tree.command(name="randomname", description="Generate a random name", guild=TEST_GUILD)
async def randomname(interaction: discord.Interaction):
    first = ["Dark", "Crazy", "Mighty", "Silent", "Quick"]
    second = ["Wolf", "Eagle", "Tiger", "Dragon", "Ghost"]
    name = random.choice(first) + random.choice(second)
    await interaction.response.send_message(f"🧙 Your random name: {name}")

# -------------- IMAGE GENERATION PLACEHOLDERS --------------

@tree.command(name="imagine", description="Generate an image from text", guild=TEST_GUILD)
@app_commands.describe(prompt="Image prompt")
async def imagine(interaction: discord.Interaction, prompt: str):
    # Placeholder for real Gemini AI text-to-image integration
    await interaction.response.send_message(f"🖼️ Imagine command received: '{prompt}'\n(Image generation coming soon!)")

@tree.command(name="describeimage", description="Describe an image from URL", guild=TEST_GUILD)
@app_commands.describe(url="Image URL")
async def describeimage(interaction: discord.Interaction, url: str):
    # Placeholder for real image description API integration
    await interaction.response.send_message(f"🔍 Description of image at {url}:\n(Description coming soon!)")

# -------------- ROLE MANAGEMENT --------------

@tree.command(name="giverole", description="Give a role to a user", guild=TEST_GUILD)
@app_commands.describe(user="User to give role", role_name="Role name")
@requires_perms(['manage_roles'])
async def giverole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    if not role:
        await ephemeral_send(interaction, f"❌ Role '{role_name}' not found.")
        return
    try:
        await user.add_roles(role)
        await interaction.response.send_message(f"✅ Given role '{role_name}' to {user}.")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to give role: {e}")

@tree.command(name="removerole", description="Remove a role from a user", guild=TEST_GUILD)
@app_commands.describe(user="User to remove role from", role_name="Role name")
@requires_perms(['manage_roles'])
async def removerole(interaction: discord.Interaction, user: discord.Member, role_name: str):
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    if not role:
        await ephemeral_send(interaction, f"❌ Role '{role_name}' not found.")
        return
    try:
        await user.remove_roles(role)
        await interaction.response.send_message(f"✅ Removed role '{role_name}' from {user}.")
    except Exception as e:
        await ephemeral_send(interaction, f"❌ Failed to remove role: {e}")

# -------------- MISC COMMANDS --------------

@tree.command(name="sayinembed", description="Bot repeats your message in an embed", guild=TEST_GUILD)
@app_commands.describe(message="Message to say")
async def sayinembed(interaction: discord.Interaction, message: str):
    embed = discord.Embed(description=message, color=discord.Color.random())
    await interaction.response.send_message(embed=embed)

# -------------- END OF COMMANDS --------------

# Run bot
bot.run(DISCORD_MANAGER_TOKEN)
