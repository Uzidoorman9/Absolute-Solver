import discord
from discord.ext import commands
import google.generativeai as genai
import os

# Keep-alive (Render users can remove this if not needed)
try:
    from keep_alive import keep_alive
    keep_alive()
except:
    pass

# Tokens (use env variables for safety)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Bot is online as {bot.user}")

@bot.command()
async def chat(ctx, *, prompt: str):
    """Talk to Gemini using !chat"""
    try:
        response = model.generate_content(prompt)
        await ctx.send(response.text)
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

bot.run(DISCORD_TOKEN)
