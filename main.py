import os
import subprocess
import discord
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Load the manager bot token and Gemini API key from environment
DISCORD_MANAGER_TOKEN = os.getenv("DISCORD_MANAGER_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

@bot.event
async def on_ready():
    print(f"✅ Manager bot logged in as {bot.user}")
    await tree.sync()

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

    # Optional: Print debug info (DO NOT log full tokens in real deployment)
    print(f"[DEBUG] Spawning child bot with prompt: {prompt[:30]}...")

    subprocess.Popen([
        "python", "child_bot.py",
        prompt,
        GEMINI_API_KEY,
        token
    ])

bot.run(DISCORD_MANAGER_TOKEN)
