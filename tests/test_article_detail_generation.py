import unittest
from unittest.mock import Mock, patch
import logging
from src.chat.openai_adapter import OpenaiAdapter
from example_usage_get_arcive import generate_detail_article
from src.chat.get_prompt import get_article_detail_prompt

class TestArticleDetailGeneration(unittest.TestCase):
    def setUp(self):
        self.logger = Mock(spec=logging.Logger)
        self.openai = Mock(spec=OpenaiAdapter)
        self.combined_content = """
        【メイン記事タイトル】気候変動による自然災害の増加
        近年、気候変動の影響により、自然災害の発生頻度が増加しています。
        特に、豪雨による水害や土砂災害のリスクが高まっているとされます。
        
        【関連記事タイトル】災害対策の重要性
        自然災害に対する事前の備えの重要性が指摘されています。
        保険加入や避難計画の策定など、具体的な対策が求められています。
        """
        self.extracted_info = "気候変動に伴う自然災害の増加により、事前の備えの重要性が高まっている"

    def test_successful_detail_article_generation(self):
        """正常な詳細情報記事生成のテスト"""
        # モックの応答を設定
        mock_response = '<detail_article>{"title": "増加する自然災害リスクと私たちの備え", "content": "近年、気候変動の影響により自然災害が増加傾向にあります。", "icebreak_usage": "最近の天候の話から自然に災害リスクの話題に展開できます。"}</detail_article>'
        self.openai.openai_chat.return_value = mock_response

        # プロンプトの準備（実際の関数と同じ形式）
        expected_prompt = get_article_detail_prompt().format(
            extracted_info=self.extracted_info,
            combined_content=self.combined_content
        )

        # テスト実行
        result = generate_detail_article(
            self.combined_content,
            self.extracted_info,
            self.openai,
            self.logger
        )

        # 検証
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "増加する自然災害リスクと私たちの備え")
        self.assertTrue("気候変動" in result["content"])
        self.assertTrue("災害リスク" in result["icebreak_usage"])
        
        # OpenAI APIの呼び出しを検証
        self.openai.openai_chat.assert_called_once_with(
            openai_model="gpt-4",
            prompt=expected_prompt,
            temperature=0.7
        )

    def test_failed_detail_article_generation(self):
        """AIからの応答が不正な場合のテスト"""
        # 不正な応答を設定
        self.openai.openai_chat.return_value = "Invalid response without tags"

        # プロンプトの準備
        expected_prompt = get_article_detail_prompt().format(
            extracted_info=self.extracted_info,
            combined_content=self.combined_content
        )

        # テスト実行
        result = generate_detail_article(
            self.combined_content,
            self.extracted_info,
            self.openai,
            self.logger
        )

        # 検証
        self.assertIsNone(result)
        self.openai.openai_chat.assert_called_once_with(
            openai_model="gpt-4",
            prompt=expected_prompt,
            temperature=0.7
        )
        self.logger.error.assert_called_with("AIの応答から必要なタグが見つかりませんでした")

    def test_error_handling(self):
        """エラー発生時の処理のテスト"""
        # エラーを発生させる
        self.openai.openai_chat.side_effect = Exception("API error")

        # プロンプトの準備
        expected_prompt = get_article_detail_prompt().format(
            extracted_info=self.extracted_info,
            combined_content=self.combined_content
        )

        # テスト実行
        result = generate_detail_article(
            self.combined_content,
            self.extracted_info,
            self.openai,
            self.logger
        )

        # 検証
        self.assertIsNone(result)
        self.openai.openai_chat.assert_called_once_with(
            openai_model="gpt-4",
            prompt=expected_prompt,
            temperature=0.7
        )
        self.logger.error.assert_called_with("詳細情報記事の生成中にエラーが発生しました: API error")

    def test_empty_content_handling(self):
        """空の入力での処理のテスト"""
        # テスト実行
        result = generate_detail_article(
            "",
            "",
            self.openai,
            self.logger
        )

        # 検証
        self.assertIsNone(result)
        self.openai.openai_chat.assert_not_called()
        self.logger.error.assert_called_with("記事内容または抽出情報が空です")

if __name__ == '__main__':
    unittest.main() 