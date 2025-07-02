import os
import subprocess
import discord
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Load manager bot token and Gemini API key from environment variables
DISCORD_MANAGER_TOKEN = os.getenv("DISCORD_MANAGER_TOKEN")

@bot.event
async def on_ready():
    print(f"Manager bot logged in as {bot.user}")
    await tree.sync()

@tree.command(name="bot", description="Spawn a Gemini chatbot using another bot's token.")
@app_commands.describe(
    prompt="Personality prompt for Gemini",
    token="Discord bot token of the bot to turn into a chatbot"
)
async def spawn_bot(interaction: discord.Interaction, prompt: str, token: str):
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        await interaction.response.send_message("❌ Gemini API key not set in environment variables.", ephemeral=True)
        return

    await interaction.response.send_message("Starting chatbot...", ephemeral=True)

    # Spawn child process passing prompt, Gemini key, and token as arguments
    subprocess.Popen([
        "python", "child_bot.py",
        prompt,
        gemini_key,
        token
    ])

bot.run(DISCORD_MANAGER_TOKEN)
