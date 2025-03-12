import unittest
import logging
from src.chat.openai_adapter import OpenaiAdapter
from src.firestore.firestore_adapter import FirestoreAdapter
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from pathlib import Path
import os
from dotenv import load_dotenv
import json
import numpy as np
from datetime import datetime, timezone, timedelta

class TestSimilarArticlesProcess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # ロギングの設定
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        cls.logger = logging.getLogger(__name__)

        # Firebase初期化
        load_dotenv()
        credentials_path = str(Path("secret-key") / f"{os.getenv('CLOUD_FIRESTORE_JSON')}.json")
        if not firebase_admin._apps:
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred)
        cls.db = firestore.client()

        # アダプターの初期化
        cls.fa = FirestoreAdapter()
        cls.openai = OpenaiAdapter()

    def setUp(self):
        """テストデータの準備"""
        # 現在時刻とexpiration_date
        now = datetime.now(timezone.utc)

        # テスト用の新規記事
        self.test_article = {
            "title": "気候変動への取り組み最前線",
            "content": "世界各国で気候変動対策が本格化しています。特に再生可能エネルギーの導入が進んでいます。",
            "icebreak_usage": "環境問題は世界的な課題となっており、気候変動対策は避けて通れないテーマです。顧客との会話で、将来のリスクや備えについて話すきっかけとして活用できます。"
        }

        # テスト用の類似記事群を準備
        self.similar_articles_data = [
            {
                "title": "気候変動への取り組み最前線",
                "content": "世界各国で気候変動対策が本格化しています。特に再生可能エネルギーの導入が進んでいます。",
                "icebreak_usage": "環境問題は世界的な課題となっており、気候変動対策は避けて通れないテーマです。顧客との会話で、将来のリスクや備えについて話すきっかけとして活用できます。",
                "retention_period_days": 30
            },
            {
                "title": "環境技術の革新的進展",
                "content": "環境技術の開発が加速しており、新たな解決策が次々と生まれています。",
                "icebreak_usage": "技術革新により、環境問題への対策が進んでいます。顧客との会話で、技術進歩と将来への備えについて話すきっかけとして活用できます。",
                "retention_period_days": 30
            }
        ]

        # 各記事のembeddingを生成
        for article in self.similar_articles_data:
            article["embedding"] = self.openai.embedding([article["icebreak_usage"]])[0]

        # Firestoreに保存
        self.fa.save_essential_info_batch(self.db, self.similar_articles_data)

    def test_vector_similarity_calculation(self):
        """ベクトル類似度の計算をテストします"""
        self.logger.info("\n=== ベクトル類似度計算のテスト開始 ===")

        # 1. 新規記事のベクトル表現を取得
        new_embedding = self.openai.embedding([self.test_article['icebreak_usage']])[0]
        self.test_article['embedding'] = new_embedding
        self.logger.info("新規記事のベクトル表現を取得しました")

        # 2. 類似度計算のテスト
        similar_articles = self.fa.get_valid_essential_info(self.db, query_vector=new_embedding)
        
        for article in similar_articles:
            embedding_array = np.array(article['embedding'])
            query_array = np.array(new_embedding)
            distance = np.linalg.norm(query_array - embedding_array)
            similarity = 1 / (1 + distance)
            
            self.logger.info(f"\n類似度計算結果:")
            self.logger.info(f"対象記事: {article['title']}")
            self.logger.info(f"類似度: {similarity:.4f}")
            
            # 類似度は0-1の範囲に収まっているはず
            self.assertGreaterEqual(similarity, 0)
            self.assertLessEqual(similarity, 1)

    def test_similarity_check_prompt(self):
        """類似性判断プロンプトの動作をテストします"""
        self.logger.info("\n=== 類似性判断プロンプトのテスト開始 ===")

        from src.chat.get_prompt import get_article_similarity_check_prompt

        # Firestoreから記事を取得
        similar_articles = self.fa.get_valid_essential_info(self.db)
        self.assertGreater(len(similar_articles), 0, "テスト用の記事が取得できませんでした")

        # 1. プロンプトの生成
        check_prompt = get_article_similarity_check_prompt().format(
            title1=self.test_article['title'],
            content1=self.test_article['content'],
            title2=similar_articles[0]['title'],
            content2=similar_articles[0]['content']
        )
        self.logger.info("類似性判断プロンプトを生成しました")

        # 2. AIによる判断の実行
        check_response = self.openai.openai_chat(
            openai_model="gpt-4o",
            prompt=check_prompt
        )
        self.assertIsNotNone(check_response)
        self.logger.info("\nAIの応答:")
        self.logger.info(check_response)

        # 3. 応答の解析
        check_start = check_response.find("<similarity_check>")
        check_end = check_response.find("</similarity_check>")
        self.assertGreaterEqual(check_start, 0)
        self.assertGreaterEqual(check_end, 0)
        
        check_json = check_response[check_start + len("<similarity_check>"):check_end].strip()
        check_result = json.loads(check_json)
        
        self.assertIn('is_similar', check_result)
        self.assertIn('reasoning', check_result)
        self.logger.info(f"\n判断結果: {'類似' if check_result['is_similar'] else '非類似'}")
        self.logger.info(f"判断理由: {check_result['reasoning']}")

    def test_article_merge_prompt(self):
        """記事結合プロンプトの動作をテストします"""
        self.logger.info("\n=== 記事結合プロンプトのテスト開始 ===")

        from src.chat.get_prompt import get_article_merge_prompt

        # Firestoreから記事を取得
        similar_articles = self.fa.get_valid_essential_info(self.db)
        self.assertGreater(len(similar_articles), 0, "テスト用の記事が取得できませんでした")

        # 1. 結合用の記事情報を準備
        articles_info = [
            {
                'title': self.test_article['title'],
                'content': self.test_article['content'],
                'icebreak_usage': self.test_article['icebreak_usage']
            },
            {
                'title': similar_articles[0]['title'],
                'content': similar_articles[0]['content'],
                'icebreak_usage': similar_articles[0]['icebreak_usage']
            }
        ]

        # 2. プロンプトの生成と実行
        merge_prompt = get_article_merge_prompt().format(
            articles_info=json.dumps(articles_info, ensure_ascii=False, indent=2)
        )
        self.logger.info("記事結合プロンプトを生成しました")

        merge_response = self.openai.openai_chat(
            openai_model="gpt-4o",
            prompt=merge_prompt
        )
        self.assertIsNotNone(merge_response)
        self.logger.info("\nAIの応答:")
        self.logger.info(merge_response)

        # 3. 応答の解析
        merge_start = merge_response.find("<merged_article>")
        merge_end = merge_response.find("</merged_article>")
        self.assertGreaterEqual(merge_start, 0)
        self.assertGreaterEqual(merge_end, 0)
        
        merge_json = merge_response[merge_start + len("<merged_article>"):merge_end].strip()
        merged_article = json.loads(merge_json)
        
        self.assertIn('title', merged_article)
        self.assertIn('content', merged_article)
        self.assertIn('icebreak_usage', merged_article)
        
        self.logger.info("\n結合結果:")
        self.logger.info(f"タイトル: {merged_article['title']}")
        self.logger.info(f"内容: {merged_article['content']}")
        self.logger.info(f"アイスブレイク活用: {merged_article['icebreak_usage']}")

    def test_full_similar_articles_process(self):
        """類似記事処理の全体フローをテストします"""
        self.logger.info("\n=== 類似記事処理の全体フローテスト開始 ===")

        # 1. 処理前の状態を確認
        self.logger.info("\n1. 処理前のFirestore状態:")
        initial_articles = self.fa.get_valid_essential_info(self.db)
        self.logger.info(f"記事数: {len(initial_articles)}")
        for article in initial_articles:
            self.logger.info(f"- {article['title']}")

        # 2. 類似記事処理の実行
        self.logger.info("\n2. 類似記事の処理を実行")
        from example_usage_get_arcive import process_similar_articles
        processed_article = process_similar_articles(
            self.test_article,
            self.openai,
            self.fa,
            self.db,
            self.logger
        )

        # 3. 処理結果の検証
        self.assertIsNotNone(processed_article)
        self.assertIn('embedding', processed_article)
        self.logger.info("\n3. 処理結果:")
        self.logger.info(f"タイトル: {processed_article['title']}")
        self.logger.info(f"内容: {processed_article['content']}")
        self.logger.info(f"アイスブレイク活用: {processed_article['icebreak_usage']}")

        # 4. 処理後のFirestore状態を確認
        self.logger.info("\n4. 処理後のFirestore状態:")
        final_articles = self.fa.get_valid_essential_info(self.db)
        self.logger.info(f"記事数: {len(final_articles)}")
        for article in final_articles:
            self.logger.info(f"- {article['title']}")

        # 5. 結果の検証
        self.assertNotEqual(
            len(initial_articles),
            len(final_articles),
            "類似記事が結合されているはずなので、記事数が減少しているはずです"
        )

    # def tearDown(self):
    #     """テストデータのクリーンアップ"""
    #     doc_ref = self.db.collection('articles').document('essential_info')
    #     doc_ref.delete()

if __name__ == '__main__':
    unittest.main() 