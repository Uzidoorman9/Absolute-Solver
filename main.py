import os
import subprocess
import discord
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DISCORD_MANAGER_TOKEN = os.getenv("DISCORD_MANAGER_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

talk_enabled_users = set()  # user IDs with talk mode on
length_limits = {}  # guild_id -> {"max_len": int, "character": str}

TEST_GUILD_ID = 1388197138487574742  # Your server ID

@bot.event
async def on_ready():
    print(f"✅ Manager bot logged in as {bot.user}")
    guild = discord.Object(id=TEST_GUILD_ID)
    await tree.sync(guild=guild)
    print(f"✅ Slash commands synced to guild {TEST_GUILD_ID}")

# /bot command: spawn child chatbot bot
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

# /ping command
@tree.command(name="ping", description="Check if the bot is online.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

# /talk_toggle command
@tree.command(name="talk_toggle", description="Toggle talk mode ON/OFF. Bot repeats your messages and deletes originals.")
async def talk_toggle(interaction: discord.Interaction):
    uid = interaction.user.id
    if uid in talk_enabled_users:
        talk_enabled_users.remove(uid)
        await interaction.response.send_message("🛑 Talk mode disabled.", ephemeral=True)
    else:
        talk_enabled_users.add(uid)
        await interaction.response.send_message("✅ Talk mode enabled.", ephemeral=True)

# /length command: set max char & character name
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

# /userinfo command
@tree.command(name="userinfo", description="Show info about a user.")
@app_commands.describe(user="User to get info about")
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

# /serverinfo command
@tree.command(name="serverinfo", description="Show info about the server.")
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

# /echo command
@tree.command(name="echo", description="Make the bot repeat your message.")
@app_commands.describe(message="Message to echo")
async def echo(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

# /clear command
@tree.command(name="clear", description="Delete messages in the channel (admin only).")
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

# /roll command - roll a dice
@tree.command(name="roll", description="Roll a dice (1-100).")
async def roll(interaction: discord.Interaction):
    import random
    result = random.randint(1, 100)
    await interaction.response.send_message(f"🎲 You rolled: {result}")

# /avatar command - show user avatar
@tree.command(name="avatar", description="Show a user's avatar.")
@app_commands.describe(user="User to show avatar of")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user}'s Avatar")
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_message(message):
    # Ignore all bots (including yourself)
    if message.author.bot:
        return

    # Talk mode: bot repeats and deletes user's message
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

bot.run(DISCORD_MANAGER_TOKEN)
