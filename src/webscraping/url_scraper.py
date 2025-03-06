import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import logging
from urllib.parse import urlparse
from .rate_limiter import RateLimiter

class URLScraper:
    def __init__(self, verify_ssl: bool = True):
        """
        URLScraperクラスの初期化
        
        Args:
            verify_ssl (bool): SSLの検証を行うかどうか。デフォルトはTrue
        """
        self.verify_ssl = verify_ssl
        self.logger = logging.getLogger(__name__)
        self.rate_limiter = RateLimiter(default_delay=0.1)  # 同一ドメインへの連続アクセス時の待機時間
        
        # セッションの初期化と共通ヘッダーの設定
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
        })
        
        # リクエストの設定
        self.request_timeout = 30  # タイムアウト（秒）
        self.max_retries = 3      # 最大リトライ回数
        self.retry_delay = 1.0    # リトライ間隔（秒）

    def scrape_urls(self, urls: List[str], selector: str) -> List[Dict[str, Any]]:
        """
        複数のURLから指定されたセレクタに基づいて要素を取得します。
        
        Args:
            urls (List[str]): スクレイピング対象のURLリスト
            selector (str): 取得したい要素のCSSセレクタ
            
        Returns:
            List[Dict[str, Any]]: 各URLからスクレイピングした結果のリスト
        """
        results = []
        
        for url in urls:
            try:
                # レート制限を適用
                self.rate_limiter.wait_if_needed(url)
                
                # HTMLを取得
                html = self._fetch_html(url)
                if html:
                    # セレクタに基づいて要素を抽出
                    elements = self._extract_elements(html, selector)
                    
                    results.append({
                        'url': url,
                        'success': True,
                        'elements': elements
                    })
                else:
                    results.append({
                        'url': url,
                        'success': False,
                        'error': 'Failed to fetch HTML'
                    })
                    
            except Exception as e:
                self.logger.error(f"Error scraping {url}: {str(e)}")
                results.append({
                    'url': url,
                    'success': False,
                    'error': str(e)
                })
                
        return results

    def _fetch_html(self, url: str) -> Optional[str]:
        """
        指定されたURLからHTMLを取得します。
        
        Args:
            url (str): 取得対象のURL
            
        Returns:
            Optional[str]: 取得したHTML。エラーの場合はNone
        """
        retries = 0
        while retries < self.max_retries:
            try:
                response = self.session.get(
                    url,
                    verify=self.verify_ssl,
                    timeout=self.request_timeout
                )
                
                # 404エラーの場合は即座に終了
                if response.status_code == 404:
                    self.logger.warning(f"Page not found: {url}")
                    return None
                
                response.raise_for_status()
                return response.text
                
            except requests.RequestException as e:
                retries += 1
                if retries < self.max_retries:
                    self.logger.warning(f"Retry {retries}/{self.max_retries}: {str(e)}")
                    self.rate_limiter.wait(self.retry_delay)
                else:
                    self.logger.error(f"Failed to fetch HTML: {str(e)}")
                    return None

    def _extract_elements(self, html: str, selector: str) -> str:
        """
        HTMLから指定されたセレクタに基づいて要素を抽出します。
        
        Args:
            html (str): 解析対象のHTML
            selector (str): 要素を抽出するためのCSSセレクタ
            
        Returns:
            str: 抽出された要素のHTML文字列
        """
        soup = BeautifulSoup(html, 'html.parser')
        elements = soup.select(selector)
        
        if not elements:
            return ''
            
        # 最初の要素のHTML文字列を返す
        return str(elements[0]) 