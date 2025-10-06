# cogs/ai_chat.py (Version 2 - 完全版)
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

from . import _utils as utils
from . import _persona_manager as persona_manager
from . import _prompt_templates as prompts

conversation_history = {}

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = genai.GenerativeModel('gemini-1.5-flash-latest')
        self.db_manager = None

    @commands.Cog.listener()
    async def on_ready(self):
        self.db_manager = self.bot.get_cog('DatabaseManager')
        if self.db_manager:
            print("Successfully linked with DatabaseManager for V2.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.content.startswith('!'):
            return
            
        asyncio.create_task(self.analyze_and_track_mood(message))
        if self.db_manager:
            asyncio.create_task(self.db_manager.add_message_to_db(message))

        if not self.bot.user.mentioned_in(message):
            return

        persona = persona_manager.get_current_persona()
        if not persona:
            await message.channel.send("（ペルソナファイルがないんだけど…？話せないわよ）")
            return
            
        user_message_clean = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()

        async with message.channel.typing():
            try:
                # STEP 1: メタ思考
                mentioned_users_text = "\n".join([f"- {user.display_name} (ID: {user.id})" for user in message.mentions if not user.bot]) or "（なし）"
                channel_id = str(message.channel.id)
                history_text = "\n".join([f"{msg['author']}: {msg['content']}" for msg in conversation_history.get(channel_id, [])])
                
                meta_prompt = prompts.META_PROMPT_TEMPLATE.format(
                    user_message=user_message_clean,
                    user_name=message.author.display_name,
                    conversation_history=history_text,
                    mentioned_users_text=mentioned_users_text
                )
                meta_response = await self.model.generate_content_async(meta_prompt)
                decision_data = self.parse_decision_text(meta_response.text)

                # STEP 2: 記憶の参照と情報収集
                target_user_id = decision_data.get("TARGET_USER_ID")
                mood_data = utils.load_mood_data().get(channel_id, {"average": 0.0})
                mood_score = mood_data["average"]
                mood_text = "ニュートラル"
                if mood_score > 0.2: mood_text = "ポジティブ"
                elif mood_score < -0.2: mood_text = "ネガティブ"

                db_memory_heading = "このチャンネルでの関連性の高い過去の会話ログ"
                search_query = user_message_clean
                if target_user_id and target_user_id.lower() != 'none':
                    try:
                        target_user_object = await self.bot.fetch_user(int(target_user_id))
                        db_memory_heading = f"ユーザー「{target_user_object.display_name}」に関する過去の発言ログ"
                        search_query = target_user_object.display_name
                    except (discord.NotFound, ValueError):
                        target_user_id = None
                
                db_memory_content = await self.db_manager.search_similar_messages(search_query, channel_id, author_id=target_user_id)
                cross_channel_memory_content = await self.db_manager.search_across_all_channels(search_query, message.guild) if not target_user_id else "（特になし）"
                
                query_embedding = await utils.get_embedding(user_message_clean)
                memory = utils.load_memory()
                user_notes = memory.get('users', {}).get(str(message.author.id), {}).get('notes', [])
                server_notes = memory.get('server', {}).get('notes', [])
                user_facts = "\n".join([f"- {n['text']}" for n in self._find_similar_notes(query_embedding, user_notes)]) or "（特になし）"
                server_facts = "\n".join([f"- {n['text']}" for n in self._find_similar_notes(query_embedding, server_notes)]) or "（特になし）"

                # STEP 3: 最終プロンプトの組み立てと応答生成
                prompt_data = {
                    "base_persona_settings": persona["settings"]["char_settings"].format(user_name=message.author.display_name),
                    "user_name": message.author.display_name,
                    "emotion": decision_data.get("EMOTION", "不明"), "intent": decision_data.get("INTENT", "不明"), "strategy": decision_data.get("STRATEGY", "不明"),
                    "mood_text": mood_text, "mood_score": mood_score, "db_memory_heading": db_memory_heading, "db_memory_content": db_memory_content,
                    "cross_channel_memory_content": cross_channel_memory_content, "user_message": user_message_clean,
                    "conversation_history": history_text or "（まだ会話してないわ）", "user_facts": user_facts, "server_facts": server_facts
                }
                final_prompt = prompts.AI_CORE_PROMPT_TEMPLATE.format(**prompt_data)
                
                response = await self.model.generate_content_async(final_prompt)
                bot_response_text = response.text.strip()
                
                await message.channel.send(bot_response_text)

                if channel_id not in conversation_history: conversation_history[channel_id] = deque(maxlen=6)
                conversation_history[channel_id].append({"author": message.author.display_name, "content": user_message_clean})
                conversation_history[channel_id].append({"author": "アタシ", "content": bot_response_text})

            except Exception as e:
                await message.channel.send(f"（うぅ…アタシの頭脳にエラーが発生したわ…: {e}）")

    def parse_decision_text(self, text):
        data = {}
        for line in text.splitlines():
            match = re.match(r'\[(.*?):(.*?)\]', line)
            if match: data[match.group(1)] = match.group(2).strip()
        return data

    def _find_similar_notes(self, query_embedding, memory_notes, top_k=3):
        if not memory_notes or query_embedding is None: return []
        notes_with_similarity = []
        for note in memory_notes:
            if 'embedding' not in note or note['embedding'] is None: continue
            note_vec = np.array(note['embedding'])
            query_vec = np.array(query_embedding)
            similarity = np.dot(query_vec, note_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(note_vec))
            notes_with_similarity.append({'text': note['text'], 'similarity': similarity})
        return sorted(notes_with_similarity, key=lambda x: x['similarity'], reverse=True)[:top_k]

    async def analyze_and_track_mood(self, message: discord.Message):
        try:
            analysis_prompt = f'ユーザーの発言: 「{message.content}」\nこの発言の感情を「Positive」「Negative」「Neutral」で判定し、-1.0から1.0のスコアを付け、以下のJSON形式で出力せよ:\n{{\n  "emotion": "判定結果",\n  "score": スコア\n}}'
            response = await self.model.generate_content_async(analysis_prompt)
            json_match = re.search(r'```json\n({.*?})\n```', response.text, re.DOTALL) or re.search(r'({.*?})', response.text, re.DOTALL)
            if json_match:
                score = float(json.loads(json_match.group(1)).get("score", 0.0))
                channel_id = str(message.channel.id)
                mood_data = utils.load_mood_data()
                if channel_id not in mood_data: mood_data[channel_id] = {"scores": [], "average": 0.0}
                scores = mood_data[channel_id].get("scores", [])
                scores.append(score)
                mood_data[channel_id]["scores"] = scores[-10:]
                mood_data[channel_id]["average"] = round(np.mean(scores), 4)
                utils.save_mood_data(mood_data)
        except Exception as e:
            print(f"Error during mood analysis: {e}")

async def setup(bot):
    await bot.add_cog(AIChat(bot))
