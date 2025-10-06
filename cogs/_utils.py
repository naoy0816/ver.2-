# cogs/_utils.py
import os
import requests
from bs4 import BeautifulSoup
import json
import google.generativeai as genai
from . import _persona_manager as persona_manager

# --- 環境変数を読み込む ---
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')
MOOD_FILE = os.path.join(DATA_DIR, 'channel_mood.json') # ★★★ 追加 ★★★

# ★★★ ここから下に関数を追加 ★★★
def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            memory = json.load(f)
            if 'relationships' not in memory: memory['relationships'] = {}
            return memory
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": [], "relationships": {}}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_mood_data():
    try:
        with open(MOOD_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_mood_data(data):
    with open(MOOD_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def get_embedding(text: str, task_type="RETRIEVAL_DOCUMENT"):
    if not text or not isinstance(text, str):
        return None
    try:
        result = await genai.embed_content_async(
            model="models/text-embedding-004",
            content=text,
            task_type=task_type
        )
        return result['embedding']
    except Exception as e:
        print(f"Embedding error: {e}")
        return None

def get_current_persona():
    persona_name = None
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            memory = json.load(f)
            persona_name = memory.get("server", {}).get("current_persona")
    except (FileNotFoundError, json.JSONDecodeError):
        pass # ファイルがなくてもエラーにしない
    
    return persona_manager.load_persona(persona_name)

# ( ... google_search, scrape_url は変更なし ... )
def google_search(query: str, num_results: int = 5) -> dict | str:
    if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
        return "（検索機能のAPIキーが設定されてないんだけど？）"
    url = "https://www.googleapis.com/customsearch/v1"
    params = {'key': SEARCH_API_KEY, 'cx': SEARCH_ENGINE_ID, 'q': query, 'num': num_results}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get('items', [])
    except requests.exceptions.RequestException as e:
        return f"（検索中にネットワークエラーよ: {e}）"
    except Exception as e:
        return f"（検索中に不明なエラーよ: {e}）"

def scrape_url(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        main_content = soup.find('main') or soup.find('article') or soup.find('body')
        if main_content:
            for tag in main_content(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
                tag.decompose()
            text = ' '.join(main_content.get_text(separator=' ', strip=True).split())
            return text[:2000]
        return "（この記事、うまく読めなかったわ…）"
    except Exception as e:
        return f"（エラーでこの記事は読めなかったわ: {e}）"
