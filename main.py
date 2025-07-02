import discord
from discord import app_commands
from discord.ext import commands
import subprocess

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    print(f"Manager bot logged in as {bot.user}")
    await tree.sync()

@tree.command(name="bot", description="Spawn a Gemini chatbot using another bot's token.")
@app_commands.describe(
    prompt="Personality prompt for Gemini",
    key="Gemini API key",
    token="Discord bot token of the bot to turn into a chatbot"
)
async def spawn_bot(interaction: discord.Interaction, prompt: str, key: str, token: str):
    await interaction.response.send_message("Starting chatbot...", ephemeral=True)
    
    # Spawn child process passing all secrets as args (secure in memory, no storage)
    subprocess.Popen([
        "python", "child_bot.py",
        prompt,
        key,
        token
    ])

bot.run("YOUR_MANAGER_BOT_TOKEN_HERE")  # <-- store this safely on your host env var
