import json
import os
from datetime import datetime
from src.webscraping.url_scraper import URLScraper
from src.webscraping.get_yahoo_feed import get_yahoo_news_feed

def get_html_string(elements):
    """
    スクレイピング結果からHTML文字列を取得します。

    Args:
        elements: スクレイピングで取得した要素（リストまたは文字列）

    Returns:
        str: HTML文字列
    """
    if isinstance(elements, list):
        for element in elements:
            if isinstance(element, dict) and element.get('tag') == 'ul':
                return element.get('html', '')
    return elements if isinstance(elements, str) else ''

def main():
    # Yahoo!ニュースのトピックスページをスクレイピング
    url = "https://news.yahoo.co.jp/topics/domestic"
    selector = "#uamods-topics > ul"
    
    scraper = URLScraper()
    print(f"URLをスクレイピング中: {url}")
    print(f"セレクタ: {selector}")
    
    results = scraper.scrape_urls([url], selector)
    result = results[0] if results else {'success': False, 'elements': ''}
    print(f"取得成功: {result['success']}")
    
    # スクレイピング結果を保存するディレクトリを作成
    os.makedirs("scraping_results", exist_ok=True)
    
    # タイムスタンプを生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 生のHTML結果を保存
    raw_html_path = f"scraping_results/yahoo_news_raw_{timestamp}.html"
    with open(raw_html_path, "w", encoding="utf-8") as f:
        f.write(result['elements'])
    print(f"生のHTML結果を保存しました: {raw_html_path}")
    
    # 記事情報を抽出
    news_items = get_yahoo_news_feed(result)
    if news_items:
        print(f"\n取得した記事数: {len(news_items)}")
        print("\n最新の記事5件:")
        for item in news_items[:5]:
            print(f"タイトル: {item['title']}")
            print(f"URL: {item['url']}")
            print("---")
        
        # JSON形式で結果を保存
        output = {
            "timestamp": timestamp,
            "url": url,
            "success": result['success'],
            "articles": news_items
        }
        
        json_path = f"scraping_results/yahoo_news_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n結果をJSONファイルに保存しました: {json_path}")
    else:
        print("記事情報の抽出に失敗しました。")

if __name__ == "__main__":
    main() 