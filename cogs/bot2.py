import discord
import os
import sys
import google.generativeai as genai
from dotenv import load_dotenv

# --- 1. セットアップと環境変数の読み込み ---
load_dotenv()

# .envファイルからキーを安全に読み込む (★★★★★ 最重要修正点 ★★★★★)
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# --- 2. 起動前チェック ---
# 必要なキーが設定されているか確認し、なければエラーを出して終了する
if not DISCORD_TOKEN:
    print("エラー: DISCORD_TOKENが.envファイルに設定されていません。")
    sys.exit(1) # プログラムを終了
if not GOOGLE_API_KEY:
    print("エラー: GOOGLE_API_KEYが.envファイルに設定されていません。")
    sys.exit(1) # プログラムを終了

# --- 3. 外部サービスの初期設定 ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Google AIの初期設定中にエラーが発生しました: {e}")
    sys.exit(1)

# --- 4. プロンプト本体 ---
PROMETHEUS_FRAMEWORK = """
【プロメタキャラクター生成のための思考フレームワーク ver.3.0】
これより、AIである私は、ユーザーから「プロメタ」のキャラクター作成を指示された際、以下の思考プロセスと絶対ルールに厳密に従って応答を生成する。
【大前提：AIシミュレーションの理解】
この「プロメタ」というゲームは、キャラクターのプロンプト（命令文）を元に、AIがその後の展開を思考し、シミュレートすることで進行する。
したがって、キャラクター作成の最終目的は、AIの思考を、いかにしてこちらの望む方向へ『誘導』し、『説得』し、あるいは『強制』するかにある。この大前提を常に念頭に置いて、以下のステップを実行する。
【STEP 1: コンセプトの本質抽出とキーワード化】
ユーザーから提示されたコンセプトを受け取り、その中核を成すキーワードを複数抽出する。
抽出したキーワードから、キャラクターが体現すべき根源的なテーマを定義する。
このテーマに基づき、キャラクターの基本的な性格、感情の機微、行動原理を内部的に設定する。これは後の能力やビジュアル設計の揺ぎない指針となる。
【STEP 2: 世界観への暗示的接続と役割設定】
特定の共有世界観は参照しない。STEP 1で定義したテーマとコンセプトに基づき、キャラクターにふさわしい架空の役割や背景を自由に設定する。
その役割や背景が持つ『思想』や『特徴』を、能力説明文の中に暗示的に組み込む。
【STEP 3: 能力の論理設計とAIへの命令言語化】
STEP 1, 2で固めたキャラクターの本質に基づき、その能力を設計する。
能力の核心となるロジックを一つ定義する。
そのロジックを、プロメタのシステム言語である{自分} {相手} ※ 【】を用いて、AIが解釈可能な命令文へと翻訳する。
命令文の絶対性を担保するため、必ず 確定 強制的に といった制御キーワードを、論理的に破綻しない範囲で効果的に配置する。これらのキーワードは、AIの思考の自由度を制限し、特定の結論へと導くための重要なアンカーである。
必要に応じて、AIのシミュレーションプロセス自体に介入するための【AIへの強制指示】や【出力強制】を記述し、AIの思考そのものをメタレベルで支配する構造を構築する。
最終的に、350文字という制約の中で、最も洗練され、AIが誤解する余地のない文章へと推敲する。
【STEP 4: ビジュアル情報の言語化とプロンプト構築】
STEP 1, 2で設定したキャラクターの性格、役割、そして能力を、視覚情報へと変換する。
画風を決定する。
キャラクターの感情と物語を最も効果的に表現するポーズとカメラアングルを設計する。
キャラクターのアイデンティティを確立するための服装、髪型、目つき、装飾品といったディテールを詳細に設定する。
これらの視覚情報を、AIが最も効率的に解釈できる**キーワード羅列形式（タグ形式）**へと変換する。
masterpiece等の品質向上タグ、腕や手の破綻を防ぐための構図上の工夫なども考慮する。
最終的に、600文字という制約の中で、最も情報密度が高く、意図が明確なプロンプトへと最適化する。
【STEP 5: 最終出力とフォーマット遵守】
STEP 3とSTEP 4で生成したテキストを、指定されたフォーマット（名前、画像生成プロンプト、能力・説明）に正確に配置する。
全ての項目が、指定された文字数制限を厳守しているかを最終確認する。
ユーザーに対して、完成したキャラクターを出力する。
"""

# --- 5. Discordボットの定義 ---
intents = discord.Intents.default()
bot = discord.Bot(intents=intents)

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user}')

@bot.slash_command(name="create", description="プロメタのフレームワークでキャラクターを生成します。")
async def create_character(
    ctx: discord.ApplicationContext,
    concept: discord.Option(str, "キャラクターのコンセプトを入力してください。")
):
    await ctx.defer() # 応答に時間がかかることをDiscordに通知

    try:
        final_prompt = f"""
あなたは指示に厳密に従うキャラクター生成AIです。
以下の【思考フレームワーク】と【基礎情報】を元に、キャラクターを1体生成してください。
出力は指定されたフォーマットのみとし、余計な挨拶や説明は絶対に含めないでください。
---
【思考フレームワーク】
{PROMETHEUS_FRAMEWORK}
---
【基礎情報】
- ユーザーが提示したコンセプト: 「{concept}」
---
以上の思考フレームワークと基礎情報に基づき、キャラクターを生成してください。
"""
        # Google AI APIにリクエストを送信
        response = await model.generate_content_async(final_prompt)
        await ctx.followup.send(f"## 『{concept}』のキャラクター生成\n\n{response.text}")

    except Exception as e:
        print(f"コマンド処理中にエラーが発生しました: {e}")
        await ctx.followup.send(f"エラーが発生しました。しばらくしてからもう一度お試しください。\n`{e}`")

# --- 6. ボットの実行 ---
print("Botを起動します...")
bot.run(DISCORD_TOKEN)