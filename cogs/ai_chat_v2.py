# cogs/ai_chat_v2.py
import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import numpy as np
import time
import re
from collections import deque

# V1のユーティリティとV2のプロンプトテンプレートをインポート
from . import _utils as utils
from . import _persona_manager as persona_manager
from . import prompt_templates as prompts
from .ai_chat import load_memory, save_memory, load_mood_data, save_mood_data

conversation_history = {}
last_intervention_time = {}
recent_messages = {}

class AIChatV2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = genai.GenerativeModel('gemini-1.5-flash-latest')
        self.db_manager = None
        self.ai_chat_cog_v1 = None # V1の関数を一部借用するため

    @commands.Cog.listener()
    async def on_ready(self):
        self.db_manager = self.bot.get_cog('DatabaseManager')
        self.ai_chat_cog_v1 = self.bot.get_cog('AIChat') # 既存Cogの関数を使う
        if self.db_manager:
            print("Successfully linked with DatabaseManager for V2.")
        if self.ai_chat_cog_v1:
             print("Successfully linked with AIChat V1 for V2.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.content.startswith('!'):
            return
            
        # V1から感情分析とDB保存のロジックを借用
        if self.ai_chat_cog_v1:
            asyncio.create_task(self.ai_chat_cog_v1.analyze_and_track_mood(message))
        if self.db_manager:
            asyncio.create_task(self.db_manager.add_message_to_db(message))

        if not self.bot.user.mentioned_in(message):
            return

        # --- ここからV2の応答ロジック ---
        persona = persona_manager.get_current_persona()
        if not persona:
            await message.channel.send("（ペルソナファイルがないんだけど…？話せないわよ）")
            return
            
        user_message_clean = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()

        async with message.channel.typing():
            try:
                # STEP 1: メタ思考
                mentioned_users_text = "\n".join([f"- {user.display_name} (ID: {user.id})" for user in message.mentions if not user.bot]) or "（なし）"
                history_text = "\n".join([f"{msg['author']}: {msg['content']}" for msg in conversation_history.get(str(message.channel.id), [])])
                
                meta_prompt = prompts.META_PROMPT_TEMPLATE.format(
                    user_message=user_message_clean,
                    user_name=message.author.display_name,
                    conversation_history=history_text,
                    mentioned_users_text=mentioned_users_text
                )
                meta_response = await self.model.generate_content_async(meta_prompt)
                decision_data = self.ai_chat_cog_v1.parse_decision_text(meta_response.text) # V1の便利なパーサーを借用

                # STEP 2: 記憶の参照と情報収集
                target_user_id = decision_data.get("TARGET_USER_ID")
                
                # ムード情報を取得
                mood_data = load_mood_data().get(str(message.channel.id), {"average": 0.0})
                mood_score = mood_data["average"]
                mood_text = "ニュートラル"
                if mood_score > 0.2: mood_text = "ポジティブ"
                elif mood_score < -0.2: mood_text = "ネガティブ"

                # DBから関連情報を検索
                db_memory_heading = "このチャンネルでの関連性の高い過去の会話ログ"
                search_query = user_message_clean
                if target_user_id and target_user_id.lower() != 'none':
                    try:
                        target_user_object = await self.bot.fetch_user(int(target_user_id))
                        db_memory_heading = f"ユーザー「{target_user_object.display_name}」に関する過去の発言ログ"
                        search_query = target_user_object.display_name
                    except (discord.NotFound, ValueError):
                        target_user_id = None
                
                db_memory_content = await self.db_manager.search_similar_messages(search_query, str(message.channel.id), author_id=target_user_id)
                cross_channel_memory_content = "（特になし）"
                if not target_user_id:
                     cross_channel_memory_content = await self.db_manager.search_across_all_channels(search_query, message.guild)

                # JSONから関連情報を検索 (V1の関数を借用)
                query_embedding = await utils.get_embedding(user_message_clean)
                memory = load_memory()
                user_notes = memory.get('users', {}).get(str(message.author.id), {}).get('notes', [])
                server_notes = memory.get('server', {}).get('notes', [])
                user_facts = "\n".join([f"- {n['text']}" for n in self.ai_chat_cog_v1._find_similar_notes(query_embedding, user_notes)]) or "（特になし）"
                server_facts = "\n".join([f"- {n['text']}" for n in self.ai_chat_cog_v1._find_similar_notes(query_embedding, server_notes)]) or "（特になし）"

                # STEP 3: 最終プロンプトの組み立てと応答生成
                prompt_data = {
                    "base_persona_settings": persona["settings"]["char_settings"].format(user_name=message.author.display_name),
                    "user_name": message.author.display_name,
                    "emotion": decision_data.get("EMOTION", "不明"),
                    "intent": decision_data.get("INTENT", "不明"),
                    "strategy": decision_data.get("STRATEGY", "不明"),
                    "mood_text": mood_text,
                    "mood_score": mood_score,
                    "db_memory_heading": db_memory_heading,
                    "db_memory_content": db_memory_content,
                    "cross_channel_memory_content": cross_channel_memory_content,
                    "user_message": user_message_clean,
                    "conversation_history": history_text or "（まだ会話してないわ）",
                    "user_facts": user_facts,
                    "server_facts": server_facts
                }
                final_prompt = prompts.AI_CORE_PROMPT_TEMPLATE.format(**prompt_data)
                
                response = await self.model.generate_content_async(final_prompt)
                bot_response_text = response.text.strip()
                
                await message.channel.send(bot_response_text)

                # 会話履歴を更新
                channel_id = str(message.channel.id)
                if channel_id not in conversation_history:
                    conversation_history[channel_id] = deque(maxlen=6)
                conversation_history[channel_id].append({"author": message.author.display_name, "content": user_message_clean})
                conversation_history[channel_id].append({"author": "アタシ", "content": bot_response_text})

            except Exception as e:
                await message.channel.send(f"（うぅ…アタシの頭脳にエラーが発生したわ…アンタのせいよ！: {e}）")

async def setup(bot):
    await bot.add_cog(AIChatV2(bot))
