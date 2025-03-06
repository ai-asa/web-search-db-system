from typing import Dict, List, Optional
from .url_scraper import URLScraper
from ..config.targets import get_yahoo_news_config, get_scraping_config
import logging
from pathlib import Path
import json

class YahooNewsScraper:
    def __init__(self):
        """
        Yahoo!ニューススクレイパーの初期化
        """
        self.url_scraper = URLScraper()
        self.yahoo_config = get_yahoo_news_config()
        self.scraping_config = get_scraping_config()
        self.logger = logging.getLogger(__name__)

    def scrape_all_categories(self, save_results: bool = False, output_dir: str = "output") -> Dict[str, List[Dict[str, str]]]:
        """
        すべてのカテゴリの記事を取得します

        Args:
            save_results (bool): 結果をファイルに保存するかどうか
            output_dir (str): 結果を保存するディレクトリ

        Returns:
            Dict[str, List[Dict[str, str]]]: カテゴリごとの記事リスト
        """
        results = {}
        for category, config in self.yahoo_config.items():
            self.logger.info(f"Scraping category: {category}")
            articles = self.scrape_category(config)
            results[category] = articles

        if save_results:
            self._save_results(results, output_dir)

        return results

    def _save_results(self, results: Dict[str, List[Dict[str, str]]], output_dir: str):
        """
        スクレイピング結果を保存します

        Args:
            results (Dict[str, List[Dict[str, str]]]): カテゴリごとの記事リスト
            output_dir (str): 出力ディレクトリ
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for category, articles in results.items():
            file_path = output_path / f"{category}_articles.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(articles, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Saved {len(articles)} articles for category {category} to {file_path}")

    def scrape_category(self, config: Dict) -> List[Dict[str, str]]:
        """
        指定されたカテゴリの記事を全ページ分取得します

        Args:
            config (Dict): カテゴリの設定情報

        Returns:
            List[Dict[str, str]]: 記事のリスト
        """
        base_url = config["base_url"]
        feed_selector = config["feed_selector"]
        articles = []
        page = 1

        while True:
            # ページURLの生成
            page_url = base_url
            if page > 1:
                page_url += self.scraping_config["page_pattern"].format(page)

            # ページのスクレイピング
            result = self.url_scraper.scrape_urls([page_url], feed_selector)
            
            if not result or not result[0]["success"] or not result[0]["elements"]:
                # 結果が空の場合は終了
                break

            # 記事の抽出
            page_articles = self._extract_articles(result[0]["elements"])
            if not page_articles:
                break

            articles.extend(page_articles)
            self.logger.info(f"Scraped page {page}, found {len(page_articles)} articles")
            page += 1

        return articles

    def _extract_articles(self, html_content: str) -> List[Dict[str, str]]:
        """
        HTML内から記事情報を抽出します

        Args:
            html_content (str): スクレイピングしたHTML

        Returns:
            List[Dict[str, str]]: 記事情報のリスト
        """
        from bs4 import BeautifulSoup
        
        articles = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 記事リンクの抽出
        for article in soup.find_all('a', href=True):
            title = article.get_text(strip=True)
            url = article['href']
            
            if title and url:
                articles.append({
                    'title': title,
                    'url': url
                })

        return articles 