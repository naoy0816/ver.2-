# cogs/ai_chat_v2.py
import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
from collections import deque

# 新しいプロンプトテンプレートをインポート
from . import prompt_templates as prompts

# 簡易的なペルソナ読み込み機能
def load_persona(name="mesugaki"):
    path = f'./cogs/personas/{name}.json'
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

# 会話履歴を保持する (簡易版)
conversation_history = {}

class AIChatV2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # ★★★ ここを修正しました ★★★
       self.model = genai.GenerativeModel('gemini-1.5-flash')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 自分自身のメッセージやコマンドは無視
        if message.author.bot or message.content.startswith('!'):
            return

        # ボットがメンションされた時だけ反応
        if not self.bot.user.mentioned_in(message):
            return

        # 会話履歴を更新
        channel_id = str(message.channel.id)
        if channel_id not in conversation_history:
            conversation_history[channel_id] = deque(maxlen=6)
        
        history_text = "\n".join([f"{msg['author']}: {msg['content']}" for msg in conversation_history[channel_id]])
        
        # --- ペルソナとプロンプトの準備 ---
        persona = load_persona("mesugaki")
        if not persona:
            await message.channel.send("（ペルソナファイルがないんだけど…？話せないわよ）")
            return

        user_message_clean = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()

        async with message.channel.typing():
            try:
                # --- プロンプトを組み立てる ---
                prompt_data = {
                    "base_persona_settings": persona["settings"]["char_settings"].format(user_name=message.author.display_name),
                    "user_name": message.author.display_name,
                    "relationship_level": 0.3, # 固定の仮データ
                    "mood_text": "ニュートラル", # 固定の仮データ
                    "user_message": user_message_clean,
                    "conversation_history": history_text or "（まだ会話してないわ）"
                }
                
                final_prompt = prompts.AI_CORE_PROMPT_TEMPLATE.format(**prompt_data)
                
                # --- Gemini APIを呼び出し、応答を生成 ---
                response = await self.model.generate_content_async(final_prompt)
                bot_response_text = response.text.strip()
                
                # --- 応答を送信 ---
                await message.channel.send(bot_response_text)

                # --- 会話履歴を保存 ---
                conversation_history[channel_id].append({"author": message.author.display_name, "content": user_message_clean})
                conversation_history[channel_id].append({"author": "アタシ", "content": bot_response_text})

            except Exception as e:
                await message.channel.send(f"（うぅ…アタシの頭脳にエラーが発生したわ…アンタのせいよ！: {e}）")

async def setup(bot):
    await bot.add_cog(AIChatV2(bot))
