import sys
import discord
import google.generativeai as genai

# --- Argument Parsing ---
try:
    prompt_base = sys.argv[1]
    gemini_key = sys.argv[2]
    discord_token = sys.argv[3]
except IndexError:
    raise ValueError("❌ Missing required arguments: prompt, Gemini key, and Discord token.")

if not gemini_key or gemini_key == "None":
    raise ValueError("❌ Gemini API key is missing or invalid.")

# --- Gemini Setup ---
genai.configure(api_key=gemini_key)
model = genai.GenerativeModel("models/gemini-1.5-flash")

# --- Discord Setup ---
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

    if bot.user.mentioned_in(message) or message.content.startswith("!"):
        try:
            full_prompt = f"{prompt_base}\nUser: {message.content}"
            response = model.generate_content(full_prompt)
            await message.channel.send(response.text)
        except Exception as e:
            await message.channel.send("❌ Something went wrong.")
            print(f"[ERROR] {e}")

bot.run(discord_token)
