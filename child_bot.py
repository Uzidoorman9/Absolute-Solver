import discord
import sys
import google.generativeai as genai

prompt_base = sys.argv[1]
gemini_key = sys.argv[2]
discord_token = sys.argv[3]

genai.configure(api_key=gemini_key)
model = genai.GenerativeModel("gemini-pro")

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"Child bot logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    # Respond to all messages or add filters here
    full_prompt = f"{prompt_base}\nUser: {message.content}"
    response = model.generate_content(full_prompt)
    await message.channel.send(response.text)

bot.run(discord_token)
