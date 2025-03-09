from typing import Dict, List, Optional
from src.webscraping.url_scraper import URLScraper
from src.config.targets import get_yahoo_news_config, get_scraping_config
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

    def scrape_article_urls(self, url: str) -> Dict[str, List[Dict[str, str]]]:
        """
        ニュース記事ページからメイン記事とピックアップ記事の情報を抽出します

        Args:
            url (str): 記事ページのURL

        Returns:
            Dict[str, List[Dict[str, str]]]: {
                'main_article': [{'title': タイトル, 'url': URL}],
                'pickup_articles': [{'title': タイトル, 'url': URL}]
            }
        """
        # HTMLの取得
        result = self.url_scraper.scrape_urls([url], 'html')
        if not result or not result[0]["success"]:
            self.logger.error(f"Failed to fetch HTML from {url}")
            return {'main_article': [], 'pickup_articles': []}
            
        html_content = result[0]["elements"]
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html_content, 'html.parser')
        results = {
            'main_article': [],
            'pickup_articles': []
        }
        
        # メイン記事の抽出
        digest_div = soup.find('div', attrs={'data-ual-view-type': 'digest'})
        if digest_div:
            # 最初のaタグを取得
            main_link = digest_div.find('a', href=True)
            if main_link:
                # aタグ内のpタグからタイトルを取得
                main_title = main_link.find('p')
                if main_title:
                    results['main_article'].append({
                        'title': main_title.get_text(strip=True),
                        'url': main_link['href']
                    })
                else:
                    self.logger.warning("Main article title (p tag) not found")
            else:
                self.logger.warning("Main article link (a tag) not found")
        else:
            self.logger.warning("Digest div not found")
            
        # ピックアップ記事の抽出
        # 1. 最初のsectionタグを探す
        # 2. その中の最初のulリストを探す
        # 3. リスト内のaタグからURLとタイトルを抽出
        section = soup.find('section')  # 最初のsectionのみ取得
        if section:
            ul = section.find('ul')  # 最初のulのみ取得
            if ul:
                for link in ul.find_all('a', href=True):
                    title = link.get_text(strip=True)
                    url = link['href']
                    if title and url:
                        results['pickup_articles'].append({
                            'title': title,
                            'url': url
                        })
        
        return results

    def scrape_article_contents(self, urls: List[str], save_results: bool = False, output_dir: str = "output") -> Dict[str, Dict[str, str]]:
        """
        指定されたURLの記事タイトルと本文を取得します

        Args:
            urls (List[str]): スクレイピング対象のURL一覧
            save_results (bool): 結果をファイルに保存するかどうか
            output_dir (str): 結果を保存するディレクトリ

        Returns:
            Dict[str, Dict[str, str]]: {
                URL: {
                    'title': タイトル,
                    'content': 本文
                }
            }
        """
        from bs4 import BeautifulSoup
        results = {}
        selectors = self.scraping_config["article_selectors"]

        for url in urls:
            self.logger.info(f"Scraping article: {url}")
            page = 1
            article_content = []
            
            while True:
                # ページURLの生成
                page_url = url
                if page > 1:
                    page_url += self.scraping_config["page_pattern"].format(page)

                # ページのスクレイピング
                result = self.url_scraper.scrape_urls([page_url], 'html')
                if not result or not result[0]["success"]:
                    break

                soup = BeautifulSoup(result[0]["elements"], 'html.parser')
                
                # タイトルの取得（最初のページのみ）
                if page == 1:
                    title_elem = soup.select_one(selectors["title"])
                    if title_elem:
                        # h1要素から直接テキストを取得
                        title = title_elem.get_text(strip=True)
                    else:
                        title = "タイトルなし"
                
                # 本文の取得
                body_elem = soup.select_one(selectors["body"])
                if not body_elem:
                    break
                
                # 本文要素内のテキストを取得
                content = []
                
                def extract_text_from_element(element):
                    """
                    要素から再帰的にテキストを抽出する補助関数
                    """
                    if isinstance(element, str):
                        text = element.strip()
                        if text:
                            return [text]
                        return []
                    
                    # リンク要素は除外
                    if element.name == 'a':
                        return []
                    
                    # その他の要素の場合、子要素を再帰的に処理
                    texts = []
                    for child in element.children:
                        texts.extend(extract_text_from_element(child))
                    return texts

                # 本文要素内のすべての子要素を再帰的に処理
                for element in body_elem.children:
                    # div要素内の全テキストを取得
                    if element.name == 'div':
                        texts = extract_text_from_element(element)
                        content.extend(texts)
                    # 直接のテキストノードも処理
                    elif isinstance(element, str) and element.strip():
                        content.append(element.strip())
                
                if content:
                    article_content.extend(content)
                page += 1

            # 結果の保存
            if article_content:
                # 空行を除去し、段落間に適切な空行を挿入
                filtered_content = [para for para in article_content if para.strip()]
                results[url] = {
                    'title': title,
                    'content': "\n\n".join(filtered_content)
                }

        if save_results:
            self._save_article_contents(results, output_dir)

        return results

    def _save_article_contents(self, results: Dict[str, Dict[str, str]], output_dir: str):
        """
        記事内容のスクレイピング結果を保存します

        Args:
            results (Dict[str, Dict[str, str]]): 記事内容の辞書
            output_dir (str): 出力ディレクトリ
        """
        from hashlib import md5
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for url, content in results.items():
            # URLからファイル名を生成
            file_name = md5(url.encode()).hexdigest()[:10] + "_article.json"
            file_path = output_path / file_name
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'url': url,
                    'title': content['title'],
                    'content': content['content']
                }, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Saved article content from {url} to {file_path}")
