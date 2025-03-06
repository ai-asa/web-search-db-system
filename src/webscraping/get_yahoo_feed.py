from typing import Dict, List, Optional
from bs4 import BeautifulSoup

def extract_news_items(html: str) -> List[Dict[str, str]]:
    """
    HTMLから記事のタイトルとURLを抽出します。

    Args:
        html (str): スクレイピングで取得したHTML文字列

    Returns:
        List[Dict[str, str]]: 記事情報のリスト。各記事は以下の形式:
        {
            "title": "記事タイトル",
            "url": "記事URL"
        }
    """
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    news_items = []
    
    # 記事のリンク要素を全て取得
    article_links = soup.find_all('a', class_='sc-1gg21n8-0')
    
    for link in article_links:
        title_element = link.find('div', class_='sc-3ls169-0')
        if title_element and link.get('href'):
            news_items.append({
                "title": title_element.text.strip(),
                "url": link['href']
            })
    
    return news_items

def get_yahoo_news_feed(scraping_result: Dict) -> Optional[List[Dict[str, str]]]:
    """
    スクレイピング結果から記事情報を抽出します。

    Args:
        scraping_result (Dict): スクレイピング結果

    Returns:
        Optional[List[Dict[str, str]]]: 記事情報のリスト。スクレイピングが失敗した場合はNone
    """
    if not scraping_result.get('success'):
        return None
        
    elements = scraping_result.get('elements')
    if not elements:
        return None
        
    return extract_news_items(elements) 