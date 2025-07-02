import sys
import discord
import google.generativeai as genai

# Read arguments from the manager bot
prompt_base = sys.argv[1]
gemini_key = sys.argv[2]
discord_token = sys.argv[3]

# Configure Gemini API with the provided key
genai.configure(api_key=gemini_key)

# Use a stable model name that works with v1
model = genai.GenerativeModel("models/gemini-1.5-flash")

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Child bot logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Only respond to messages that mention the bot or start with "!"
    if bot.user.mentioned_in(message) or message.content.startswith("!"):
        try:
            full_prompt = f"{prompt_base}\nUser: {message.content}"
            response = model.generate_content(full_prompt)
            await message.channel.send(response.text)
        except Exception as e:
            await message.channel.send(f"❌ Error: {e}")
            print(f"Error: {e}")

bot.run(discord_token)
