import os
import subprocess
import discord
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")
    await tree.sync()

@tree.command(name="bot", description="Turn a bot into a Gemini chatbot.")
@app_commands.describe(prompt="Chatbot personality", token="Target bot's token")
async def spawn_bot(interaction: discord.Interaction, prompt: str, token: str):
    await interaction.response.send_message("📦 Spawning chatbot...", ephemeral=True)
    
    subprocess.Popen([
        "python", "child_bot.py",
        prompt,
        GEMINI_KEY,
        token
    ])
