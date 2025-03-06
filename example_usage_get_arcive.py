from src.chat.openai_adapter import OpenaiAdapter
from src.chat.get_prompt import (
    get_customer_info_analysis_prompt,
    get_icebreak_suggestion_prompt,
    get_search_keywords_prompt,
    get_web_research_summarize_prompt
)
from src.websearch.web_search import WebSearch
from src.tiktoken import count_tokens
import json
from dotenv import load_dotenv
import os
import time
import logging
from src.webscraping.yahoo_news_scraper import YahooNewsScraper
import json
import firebase_admin
from firebase_admin import firestore
from firebase_admin import credentials
from src.firestore.firestore_adapter import FirestoreAdapter

credentials_path = f"./secret-key/{os.getenv('CLOUD_FIRESTORE_JSON')}.json"
cred = credentials.Certificate(credentials_path)
app = firebase_admin.initialize_app(cred)
db = firestore.client()


# 開発対象

# 保険に関連する可能性のある記事を蓄積する機能を考える
# アイスブレイク用のニュース記事収集システム
# ・スクレイピング先のサイトを選定しておく
# yahoo newsをスクレイピングする → 国内、国際、経済の3トピック
# ・スクレイピング結果から、ニュース記事(とURL)を選定する→AI使用
# 詳細
# ・全ページの記事を取得
# ・記事のタイトルとURLを取得

# ・データベースで取得済みの記事を除外する → 過去に一度でも取得した記事は除外する
# ・AIで関係しそうな記事の選択
# ・URL先の「・・・記事全文を読む」のURLから記事全文を取得
# ・AIで関係しそうな記事の選択
# ・データベースをチェックし、取得済みの記事かどうかをチェックする→記事タイトル及びURL検索
# ・取得済みでなければ、スクレイピング
# ・スクレイピング結果から、保険営業に関連する記事であったかどうかを判定
# ・判定結果が正なら、記事のタイトルとURLをデータベースに保存
# ・記事の中で、保険営業に関係していそうな本質情報があれば、ウェブ検索する
# ・ウェブ検索結果を要約し、保険営業に関係している本質情報だった場合は、保存期間を設定してデータベースに保存

# ・いくつかのバッチ単位で記事の内容をAIで要約してデータベースに保存
# ・時事性の強い記事は1週間経過で削除
# ・制度変更など、時事性が強くない記事は1年間は削除しない
# ・使用時はデータベースからベクトル検索
# ・理由を添えて記事を選定
# ・記事毎にアイスブレイク用のテキストを生成

def setup_logging():
    """ロギングの設定"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def display_results(results: dict):
    """
    スクレイピング結果を表示します

    Args:
        results (dict): カテゴリごとの記事リスト
    """
    for category, articles in results.items():
        print(f"\n【{category}】の記事一覧:")
        print(f"取得記事数: {len(articles)}件")
        for article in articles[:5]:  # 最初の5件のみ表示
            print(f"- {article['title']}")
            print(f"  URL: {article['url']}")
        if len(articles) > 5:
            print(f"  ... 他 {len(articles) - 5}件")

def main():
    """メイン処理"""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        # スクレイパーの初期化
        yns = YahooNewsScraper()
        
        # すべてのカテゴリの記事を取得（結果を保存）
        logger.info("Starting to scrape Yahoo News categories...")
        results = yns.scrape_all_categories(save_results=True)
        
        # 結果の表示
        display_results(results)

    except Exception as e:
        logger.error(f"Error occurred: {str(e)}", exc_info=True)
        raise



# def collect_customer_info():
#     """顧客情報を収集するための質問を表示する"""
#     print("\nアシスタント：以下の情報を教えていただけますでしょうか？")
#     print("・お客様の年齢")
#     print("・お客様の性別")
#     print("・ご家族構成（独身・家族）")
#     print("・お仕事（サラリーマン・自営業、職種）")
#     print("・お住まいの都道府県")
    
#     # ユーザーからの入力を受け取る
#     customer_info = input("\nユーザー：")
#     return customer_info

# def main():
#     load_dotenv()
#     custom_search_engine_id = os.getenv("GOOGLE_CSE_ID")
#     # OpenAIアダプターとWebSearchのインスタンスを作成
#     openai = OpenaiAdapter()
#     web_search = WebSearch(default_engine="duckduckgo")
#     # web_search.scraper = WebScraper(verify_ssl=False)  # SSL検証を無効化
#     fa = FirestoreAdapter(db)
    
#     while True:
#         start_time_total = time.time()
        
#         # 顧客情報の収集
#         customer_input = collect_customer_info()
        
#         # 終了コマンドの確認
#         if customer_input.lower() == 'quit':
#             print("システムを終了します。")
#             break
        
#         # 顧客情報の整理
#         start_time = time.time()
#         analysis_response = openai.openai_chat(
#             openai_model="gpt-4o",
#             prompt=get_customer_info_analysis_prompt() + f"\n\n入力情報: {customer_input}"
#         )
#         print(f"顧客情報分析処理時間: {time.time() - start_time:.2f}秒")
        
#         # 整理された顧客情報の抽出
#         try:
#             info_start = analysis_response.find("<customer_info>") + len("<customer_info>")
#             info_end = analysis_response.find("</customer_info>")
#             customer_info = json.loads(analysis_response[info_start:info_end])
            
#             # 整理された情報の表示
#             print("\n【整理された顧客情報】")
#             print(f"年齢：{customer_info['age']}")
#             print(f"性別：{customer_info['gender']}")
#             print(f"家族構成：{customer_info['family_status']}")
#             print(f"職業：{customer_info['occupation']['type']} ({customer_info['occupation']['industry']})")
#             print(f"居住地：{customer_info['location']}")
            
#             # アイスブレイク情報の収集
#             print("\n【アイスブレイク情報の収集中...】")
            
#             # 検索キーワードの生成
#             start_time = time.time()
#             search_keywords_prompt = get_search_keywords_prompt()
#             search_keywords_response = openai.openai_chat(
#                 openai_model="gpt-4o",
#                 prompt=search_keywords_prompt + f"\n\n顧客情報: {json.dumps(customer_info, ensure_ascii=False)}"
#             )
#             print(f"検索キーワード生成処理時間: {time.time() - start_time:.2f}秒")
            
#             try:
#                 keywords_start = search_keywords_response.find("<search_keywords>") + len("<search_keywords>")
#                 keywords_end = search_keywords_response.find("</search_keywords>")
#                 search_keywords = json.loads(search_keywords_response[keywords_start:keywords_end])
                
#                 # Web検索の実行
#                 search_results = {}
#                 for category, keyword in search_keywords.items():
#                     # print(f"\n{category}に関する情報を検索中: {keyword}")
                    
#                     scrape_options = {
#                         "save_json": False,
#                         "save_markdown": False,
#                         "exclude_links": True,
#                         "max_depth": 20
#                     }
                    
#                     # Web検索を実行し、Markdown形式でデータを取得
#                     start_time = time.time()
#                     search_result = web_search.search_and_standardize(
#                         keyword,
#                         scrape_urls=True,
#                         scrape_options=scrape_options,
#                         max_results=4
#                     )
#                     print(f"Web検索処理時間: {time.time() - start_time:.2f}秒")
                    
#                     # 検索結果とスクレイピングデータを整理
#                     research_content = f"検索キーワード: {keyword}\n\n"
#                     current_chunk = research_content
#                     intermediate_summaries = []
                    
#                     # スクレイピング結果の確認
#                     has_valid_content = False
#                     if search_result.get("scraped_data"):
#                         for url, data in search_result["scraped_data"].items():
#                             if data and "markdown_data" in data:
#                                 has_valid_content = True
#                                 new_content = f"\n---\nURL: {url}\n{data['markdown_data']}\n"
#                                 # トークン数を計算
#                                 if count_tokens(current_chunk + new_content) > 30000:
#                                     # 現在のチャンクを中間要約
#                                     intermediate_summary = openai.openai_chat(
#                                         openai_model="gpt-4o",
#                                         prompt=get_web_research_summarize_prompt() + f"\n\n{current_chunk}"
#                                     )
#                                     intermediate_summaries.append(intermediate_summary)
#                                     # 新しいチャンクを開始
#                                     current_chunk = new_content
#                                 else:
#                                     current_chunk += new_content
                    
#                     if has_valid_content:
#                         # 最後のチャンクを処理
#                         if current_chunk:
#                             intermediate_summary = openai.openai_chat(
#                                 openai_model="gpt-4o",
#                                 prompt=get_web_research_summarize_prompt() + f"\n\n{current_chunk}"
#                             )
#                             intermediate_summaries.append(intermediate_summary)
                        
#                         # すべての中間要約を結合
#                         summary = "\n\n".join(intermediate_summaries)
#                         print(f"検索結果整理処理時間: {time.time() - start_time:.2f}秒")
#                     else:
#                         summary = "情報の取得に失敗しました。"
                    
#                     search_results[category] = summary
                
#                 # アイスブレイクの提案生成
#                 start_time = time.time()
#                 icebreak_prompt = get_icebreak_suggestion_prompt()
#                 icebreak_context = {
#                     "customer_info": customer_info,
#                     "search_results": search_results
#                 }
                
#                 icebreak_suggestions = openai.openai_chat(
#                     openai_model="gpt-4o",
#                     prompt=icebreak_prompt + f"\n\nコンテキスト: {json.dumps(icebreak_context, ensure_ascii=False)}"
#                 )
#                 print(f"アイスブレイク提案生成処理時間: {time.time() - start_time:.2f}秒")

#                 # JSONデータの抽出と解析
#                 try:
#                     suggestions_start = icebreak_suggestions.find("<icebreak_suggestions>") + len("<icebreak_suggestions>")
#                     suggestions_end = icebreak_suggestions.find("</icebreak_suggestions>")
#                     suggestions_data = json.loads(icebreak_suggestions[suggestions_start:suggestions_end])

#                     # 整形された形式で出力
#                     print("\n【アイスブレイク提案】")
                    
#                     for topic, data in suggestions_data["topics"].items():
#                         topic_names = {
#                             "weather": "天候に関する話題",
#                             "local": "地域に関する話題",
#                             "news": "ニュースに関する話題",
#                             "seasonal": "季節に関する話題"
#                         }
                        
#                         print(f"\n{topic_names.get(topic, topic)}")
#                         print("- 切り出し方：")
#                         print(f"{data['starter']}")
#                         print("\n- 情報源：")
#                         print(f"{data['source']}")
#                         print("\n- 保険への展開：")
#                         print(f"{data['insurance_bridge']}")
                    
#                     print("\n【最適なアプローチ】")
#                     print(suggestions_data["best_approach"])
#                     print(f"\n総処理時間: {time.time() - start_time_total:.2f}秒")

#                 except json.JSONDecodeError:
#                     print("エラー：アイスブレイク提案の解析に失敗しました。")
#                     print(icebreak_suggestions)  # デバッグ用に元のレスポンスを表示
            
#             except json.JSONDecodeError:
#                 print("エラー：検索キーワードの解析に失敗しました。")
#             except Exception as e:
#                 print(f"エラー：検索処理中にエラーが発生しました: {str(e)}")
            
#             # 続けて別の顧客情報を入力するか確認
#             continue_input = input("\n別の顧客情報を入力しますか？ (y/n): ")
#             if continue_input.lower() != 'y':
#                 print("システムを終了します。")
#                 break
                
#         except json.JSONDecodeError:
#             print("エラー：顧客情報の解析に失敗しました。")
#             print("もう一度入力をお願いします。")
#             continue
#         except Exception as e:
#             print(f"エラー：処理中にエラーが発生しました: {str(e)}")
#             print("もう一度入力をお願いします。")
#             continue

if __name__ == "__main__":
    main() 