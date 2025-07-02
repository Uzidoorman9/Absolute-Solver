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

running_bots = []

@bot.event
async def on_ready():
    print(f"🤖 Manager Bot logged in as {bot.user}")
    await tree.sync()

@tree.command(name="bot", description="Turn a bot into a Gemini chatbot.")
@app_commands.describe(prompt="Chatbot personality", token="Target bot's Discord token")
async def spawn_bot(interaction: discord.Interaction, prompt: str, token: str):
    await interaction.response.send_message("📦 Spawning chatbot...", ephemeral=True)

    proc = subprocess.Popen([
        "python", "child_bot.py",
        prompt,
        GEMINI_KEY,
        token
    ])

    running_bots.append({
        "token": token,
        "prompt": prompt,
        "pid": proc.pid
    })

@tree.command(name="list_bots", description="List all running chatbot instances.")
async def list_bots(interaction: discord.Interaction):
    if not running_bots:
        await interaction.response.send_message("No running chatbots.")
        return

    msg = "\n".join([f"• PID: {b['pid']} | Prompt: {b['prompt'][:30]}..." for b in running_bots])
    await interaction.response.send_message(f"🧠 Active chatbots:\n{msg}")

@tree.command(name="stop_bot", description="Stop a running chatbot by PID.")
@app_commands.describe(pid="Process ID of the chatbot to stop")
async def stop_bot(interaction: discord.Interaction, pid: int):
    stopped = False
    for bot_info in running_bots:
        if bot_info["pid"] == pid:
            try:
                # Terminate the process
                import signal, psutil
                p = psutil.Process(pid)
                p.terminate()
                running_bots.remove(bot_info)
                stopped = True
                await interaction.response.send_message(f"✅ Stopped chatbot PID {pid}")
            except Exception as e:
                await interaction.response.send_message(f"❌ Could not stop bot: {e}")
            break
    if not stopped:
        await interaction.response.send_message(f"❌ No chatbot found with PID {pid}")

bot.run(os.getenv("DISCORD_TOKEN"))
