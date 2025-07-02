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

@bot.event
async def on_ready():
    print(f"✅ Manager bot logged in as {bot.user}")
    await tree.sync()

# --- Spawn a chatbot ---
@tree.command(name="bot", description="Spawn a Gemini chatbot using another bot's token.")
@app_commands.describe(
    prompt="The personality or behavior prompt for the chatbot",
    token="The Discord token of the bot to turn into a chatbot"
)
async def spawn_bot(interaction: discord.Interaction, prompt: str, token: str):
    if not GEMINI_API_KEY:
        await interaction.response.send_message("❌ Gemini API key not set in environment variables.", ephemeral=True)
        return
    await interaction.response.send_message("🚀 Starting chatbot...", ephemeral=True)
    subprocess.Popen([
        "python", "child_bot.py",
        prompt,
        GEMINI_API_KEY,
        token
    ])

# --- Ping test ---
@tree.command(name="ping", description="Check if the bot is online.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

# --- Toggle talk mode ---
@tree.command(name="talk_toggle", description="Toggle talk mode ON/OFF. Bot will say your messages and delete yours.")
async def talk_toggle(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in talk_enabled_users:
        talk_enabled_users.remove(user_id)
        await interaction.response.send_message("🛑 Talk mode disabled.", ephemeral=True)
    else:
        talk_enabled_users.add(user_id)
        await interaction.response.send_message("✅ Talk mode enabled.", ephemeral=True)

# --- Set length and character name ---
@tree.command(name="length", description="Set chat length limit and character name.")
@app_commands.describe(
    max_length="Maximum allowed characters per message",
    character="Character name users should roleplay as"
)
async def set_length(interaction: discord.Interaction, max_length: int, character: str):
    if max_length <= 0:
        await interaction.response.send_message("❌ Max length must be a positive number.", ephemeral=True)
        return
    length_limits[interaction.guild_id] = {"max_len": max_length, "character": character}
    await interaction.response.send_message(
        f"✅ Chat length limit set to {max_length} characters. Users must roleplay as **{character}**."
    )

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Talk mode: repeat & delete message
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
