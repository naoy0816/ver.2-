# bot.py
import discord
from discord.ext import commands
import os
import asyncio
import google.generativeai as genai

# Botの基本的な設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def setup_hook():
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    print("Google Generative AI configured.")
    print('------------------------------------------------------')
    
    # ★★★ ここを修正 ★★★
    # 新しいCogを読み込むようにファイル名を指定
    cog_to_load = 'cogs.ai_chat_v2' 
    try:
        await bot.load_extension(cog_to_load)
        print(f'✅ Successfully loaded: {cog_to_load}.py')
    except Exception as e:
        print(f'❌ Failed to load {cog_to_load}.py: {e}')
    
    # 他のCogも必要であればここで読み込む
    # await bot.load_extension('cogs.commands')
    
    print('------------------------------------------------------')
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

@bot.event
async def on_ready():
    print(f'Logged in as: {bot.user.name}')
    print('Bot is now online and ready!')

# Botを起動
async def main():
    token = os.getenv('DISCORD_BOT_TOKEN')
    if token is None:
        print("Error: DISCORD_BOT_TOKEN is not set in environment variables.")
        return
    
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot is shutting down...")
