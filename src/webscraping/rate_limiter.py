from urllib.parse import urlparse
import time
from collections import defaultdict
from typing import Dict
from datetime import datetime
# import asyncio

class RateLimiter:
    def __init__(self, default_delay: float = 0.1):
        """
        RateLimiterの初期化

        Args:
            default_delay (float): 同じドメインへの連続リクエスト時の最小待機時間（秒）
        """
        self.last_request_time = defaultdict(float)
        self.default_delay = default_delay
        self.last_domain = None  # 直前にリクエストしたドメインを保持
        # self.lock = asyncio.Lock()  # 非同期ロック

    def wait_if_needed(self, url: str):
        """
        同じドメインに連続してリクエストする場合のみ、待機時間を確保する

        Args:
            url (str): リクエスト先のURL
        """
        domain = urlparse(url).netloc
        current_time = time.time()
        
        # 直前のリクエストが同じドメインだった場合のみ待機
        if domain == self.last_domain:
            elapsed_time = current_time - self.last_request_time[domain]
            if elapsed_time < self.default_delay:
                wait_time = self.default_delay - elapsed_time
                time.sleep(wait_time)
        
        # 現在の情報を記録
        self.last_request_time[domain] = current_time
        self.last_domain = domain

    def wait(self, delay: float):
        """
        指定された時間だけ待機します

        Args:
            delay (float): 待機時間（秒）
        """
        time.sleep(delay)

    def get_delay_for_domain(self, domain: str) -> float:
        """
        指定されたドメインの待機時間を取得します

        Args:
            domain (str): 対象ドメイン

        Returns:
            float: 待機時間（秒）
        """
        return self.default_delay

    # async def wait_if_needed_async(self, url):
    #     """同じドメインに連続してリクエストする場合のみ、非同期で待機時間を確保する

    #     Args:
    #         url (str): リクエスト先のURL
    #     """
    #     domain = urlparse(url).netloc
    #     current_time = time.time()
        
    #     async with self.lock:
    #         # 直前のリクエストが同じドメインだった場合のみ待機
    #         if domain == self.last_domain:
    #             elapsed_time = current_time - self.last_request_time[domain]
    #             if elapsed_time < self.default_delay:
    #                 wait_time = self.default_delay - elapsed_time
    #                 await asyncio.sleep(wait_time)
            
    #         # 現在の情報を記録
    #         self.last_request_time[domain] = time.time()
    #         self.last_domain = domain 