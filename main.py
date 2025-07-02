import discord
from discord.ext import commands
import google.generativeai as genai
import os

# Setup
DISCORD_TOKEN = "YOUR_DISCORD_BOT_TOKEN"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"

# Gemini setup
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# Intents and Bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def chat(ctx, *, prompt: str):
    """Use /chat [message] to talk to the bot."""
    try:
        response = model.generate_content(prompt)
        await ctx.send(response.text)
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

bot.run(DISCORD_TOKEN)
