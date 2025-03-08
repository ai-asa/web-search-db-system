from src.chat.openai_adapter import OpenaiAdapter
from src.chat.get_prompt import (
    get_customer_info_analysis_prompt,
    get_icebreak_suggestion_prompt,
    get_search_keywords_prompt,
    get_web_research_summarize_prompt,
    get_article_selection_prompt,
    get_article_grouping_prompt
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
from pathlib import Path
import platform

# 認証情報のパスを設定
credentials_path = str(Path("secret-key") / f"{os.getenv('CLOUD_FIRESTORE_JSON')}.json")
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
# ・選択した記事のタイトルとURLをデータベースに保存
# ・記事の選定を行う → 記事の内容被り対策

# 特定のURLから「・・・記事全文を読む」のURLを取得
# 同様のページから、関連記事のURLを取得

# 記事の本文を取得するスクリプトの作成


# グループトピックについて
# 記事タイトルから、本質情報を含んでいるかを判断する？
# 記事が複数ある場合はそれでできそうだけど、数が少ない場合はそれが難しそう
# →　記事を全て読み込む？？　→　コストが大きい　→　2つだけ記事を読み込んで、本質情報が含まれているかを判断する
# 含まれていない場合、そのグループトピックは除外する
# 含まれている場合、以下の処理を行う
# 同じグループの記事数が複数ある場合、被るサブトピックは全て排除する
# →　5件以下の場合はサブトピックを含め、全件を分割読込して、本質情報を抽出する　→　最後に本質情報について十分な情報があるかも判断し、無い場合は検索キーワードの抽出、検索による補完
# →　5件以上の場合は、サブトピックを除外し、全件を分割読込して、本質情報を抽出する

# 単体トピックについて
# →　メイントピックの記事のみを読み込んで、保険営業アイスブレイクに使える時事ネタを得たいという視点における本質情報が記事に存在するかを分析する
# →　存在し、サブトピックがある場合は、メインとサブの両方を読み込んでAIによる本質情報の抽出を行う。十分な情報があるかどうかも同時に判断し、十分な情報がない場合は、検索キーワードの抽出、検索による補完
# →　存在し、サブトピックがない場合は、本質情報について検索キーワードをAI生成し、検索結果のスクレイピングで、対象情報を整理する



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

def scrape_news_articles(yns: YahooNewsScraper) -> dict:
    """
    Yahoo Newsから記事をスクレイピングします

    Args:
        yns (YahooNewsScraper): YahooNewsScraperインスタンス

    Returns:
        dict: カテゴリごとの記事リスト
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting to scrape Yahoo News categories...")
    return yns.scrape_all_categories(save_results=True)

def filter_new_articles(articles_by_category: dict, fa: FirestoreAdapter) -> list:
    """
    既存の記事を除外し、新規記事のみをフィルタリングします

    Args:
        articles_by_category (dict): カテゴリごとの記事リスト
        fa (FirestoreAdapter): FirestoreAdapterインスタンス

    Returns:
        list: 新規記事のリスト
    """
    logger = logging.getLogger(__name__)
    logger.info("Fetching existing articles from Firestore...")
    existing_articles = fa.get_discovered_articles(db)
    existing_urls = {article['url'] for article in existing_articles}

    new_articles = []
    for category, articles in articles_by_category.items():
        for article in articles:
            if article['url'] not in existing_urls:
                new_articles.append(article)
                logger.info(f"Found new article: {article['title']}")

    return new_articles

def process_article_batch(batch_articles: list, batch_start: int) -> list:
    """
    記事バッチを処理し、関連する記事を選別します

    Args:
        batch_articles (list): 処理する記事のバッチ
        batch_start (int): バッチの開始インデックス

    Returns:
        list: 選別された記事のリスト
    """
    logger = logging.getLogger(__name__)
    numbered_articles = []
    article_text = ""

    for i, article in enumerate(batch_articles, batch_start + 1):
        numbered_articles.append({
            "number": i,
            "title": article["title"],
            "url": article["url"]
        })
        article_text += f"{i}. {article['title']}\n"

    openai = OpenaiAdapter()
    selection_prompt = get_article_selection_prompt()
    selection_response = openai.openai_chat(
        openai_model="gpt-4o",
        prompt=selection_prompt + "\n\n" + article_text
    )

    try:
        selection_start = selection_response.find("<selected_articles>") + len("<selected_articles>")
        selection_end = selection_response.find("</selected_articles>")
        selected_numbers_str = selection_response[selection_start:selection_end].strip()

        selected_numbers_str = selected_numbers_str.replace('[', '').replace(']', '')
        selected_numbers = []
        if selected_numbers_str:
            for num_str in selected_numbers_str.replace(',', ' ').split():
                try:
                    num = int(num_str.strip())
                    selected_numbers.append(num)
                except ValueError as ve:
                    logger.warning(f"Invalid number format found: {num_str}")
                    continue

        reasoning_start = selection_response.find("<reasoning>") + len("<reasoning>")
        reasoning_end = selection_response.find("</reasoning>")
        selection_reasoning = selection_response[reasoning_start:reasoning_end].strip()

        if not selected_numbers:
            logger.info("\n選別結果：")
            logger.info("保険営業の時事ネタとして適切な記事は見つかりませんでした。")
            logger.info(f"\n理由：\n{selection_reasoning}")
            return []

        logger.info("\n選別結果：")
        logger.info(f"保険営業の時事ネタとして {len(selected_numbers)} 件の記事が選択されました。")

        batch_selected_articles = []
        for num in selected_numbers:
            article = next((a for a in numbered_articles if a["number"] == num), None)
            if article:
                batch_selected_articles.append({
                    "title": article["title"],
                    "url": article["url"]
                })
                logger.info(f"\n{article['number']}. {article['title']}")
                logger.info(f"   URL: {article['url']}")

        logger.info(f"\n選択理由：\n{selection_reasoning}")
        return batch_selected_articles

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error processing selection: {str(e)}")
        logger.error(f"Raw response: {selection_response}")
        return []

def select_relevant_articles(new_articles: list, batch_size: int = 50) -> list:
    """
    新規記事から関連する記事を選別します

    Args:
        new_articles (list): 新規記事のリスト
        batch_size (int, optional): バッチサイズ. デフォルトは50

    Returns:
        list: 選別された記事のリスト
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting article selection process...")
    all_selected_articles = []

    for batch_start in range(0, len(new_articles), batch_size):
        batch_end = min(batch_start + batch_size, len(new_articles))
        batch_articles = new_articles[batch_start:batch_end]
        
        logger.info(f"Processing batch {batch_start//batch_size + 1} ({batch_start+1} to {batch_end} of {len(new_articles)} articles)")
        batch_selected_articles = process_article_batch(batch_articles, batch_start)
        all_selected_articles.extend(batch_selected_articles)

    return all_selected_articles

def save_new_referenced_articles(selected_articles: list, fa: FirestoreAdapter):
    """
    選別された新規記事を参照記事として保存します

    Args:
        selected_articles (list): 選別された記事のリスト
        fa (FirestoreAdapter): FirestoreAdapterインスタンス
    """
    logger = logging.getLogger(__name__)
    if not selected_articles:
        return

    logger.info("過去の参照記事を取得中...")
    referenced_articles = fa.get_referenced_articles(db)
    referenced_urls = {article['url'] for article in referenced_articles}

    new_referenced_articles = [
        article for article in selected_articles
        if article['url'] not in referenced_urls
    ]

    if new_referenced_articles:
        logger.info(f"{len(new_referenced_articles)}件の新規参照記事を保存中...")
        fa.save_referenced_articles_batch(db, new_referenced_articles)
        logger.info("新規参照記事の保存が完了しました。")
    else:
        logger.info("新規の参照記事はありませんでした。")

def process_article_groups(selected_articles: list) -> dict:
    """
    選別された記事から、同一内容の記事をグループ化します

    Args:
        selected_articles (list): 選別された記事のリスト

    Returns:
        dict: グループ化された記事の情報
    """
    logger = logging.getLogger(__name__)
    numbered_articles = []
    article_text = ""

    for i, article in enumerate(selected_articles, 1):
        numbered_articles.append({
            "number": i,
            "title": article["title"],
            "url": article["url"]
        })
        article_text += f"{i}. {article['title']}\n"

    openai = OpenaiAdapter()
    grouping_prompt = get_article_grouping_prompt()
    grouping_response = openai.openai_chat(
        openai_model="gpt-4",
        prompt=grouping_prompt + "\n\n" + article_text
    )

    try:
        reasoning_start = grouping_response.find("<reasoning>") + len("<reasoning>")
        reasoning_end = grouping_response.find("</reasoning>")
        grouping_reasoning = grouping_response[reasoning_start:reasoning_end].strip()

        groups_start = grouping_response.find("<grouped_articles>") + len("<grouped_articles>")
        groups_end = grouping_response.find("</grouped_articles>")
        groups_str = grouping_response[groups_start:groups_end].strip()

        groups = json.loads(groups_str)

        logger.info("\nグループ化結果：")
        logger.info(f"\n理由：\n{grouping_reasoning}")
        
        # 各グループの記事を表示
        for group_name, group_info in groups.items():
            if group_name == "others":
                logger.info(f"\n【その他の個別記事】:")
            else:
                logger.info(f"\n【{group_info['title']}】:")
            
            for num in group_info['articles']:
                article = next((a for a in numbered_articles if a["number"] == num), None)
                if article:
                    logger.info(f"- {article['title']}")
                    logger.info(f"  URL: {article['url']}")

        # グループ化された記事の情報を返す
        return {
            "reasoning": grouping_reasoning,
            "groups": groups,
            "articles": numbered_articles
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error processing groups: {str(e)}")
        logger.error(f"Raw response: {grouping_response}")
        return None

def main():
    """メイン処理"""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        # 初期化
        yns = YahooNewsScraper()
        fa = FirestoreAdapter()

        # 記事収集パイプライン
        scraped_articles = scrape_news_articles(yns)
        new_articles = filter_new_articles(scraped_articles, fa)

        if new_articles:
            fa.save_discovered_articles_batch(db, new_articles)
            logger.info(f"Saved {len(new_articles)} new articles in batch")

            selected_articles = select_relevant_articles(new_articles)
            if selected_articles:
                # 選別された記事をグループ化
                grouped_results = process_article_groups(selected_articles)
                if grouped_results:
                    # グループ化された記事を保存
                    save_new_referenced_articles(selected_articles, fa)

    except Exception as e:
        logger.error(f"Error occurred: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main() 