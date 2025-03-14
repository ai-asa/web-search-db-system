# 標準ライブラリ
import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# 自作モジュール
from src.chat.openai_adapter import OpenaiAdapter
from src.chat.get_prompt import (
    get_initial_article_analysis_prompt,
    get_relevance_validation_prompt
)

# テスト対象の関数をインポート
from example_usage_get_arcive import analyze_individual_article_content, extract_tagged_json

def setup_logging():
    """ロギングの設定"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def test_analyze_article_directly():
    """OpenAIの応答を直接確認するためのテスト"""
    # 環境変数の読み込み
    load_dotenv()
    
    # ロガーの設定
    logger = setup_logging()
    logger.info("OpenAI応答の直接テストを開始します")
    
    # テスト用の記事データ
    test_article = {
        "title":"30代シングルマザー「息子の高校“入学金”が払えない」“高校授業料無償化”の落とし穴…母子が行政の“たらい回し”の果て「生活保護」選んだ理由",
        "content": """今、国政の場で「高校授業料無償化」へ向けた議論が活発化しています。特に低所得世帯にとっては朗報ですが、何より重要なのは、すべての子どもが学ぶ機会を実質的に保障されるような制度設計がなされることです。
        先日、大阪府大阪市に住む母子家庭のシングルマザーのミサさん（仮名・30代）から私の行政書士事務所に悲痛な相談がありました。一人息子・トオルくん（仮名・15歳）の高校入試が終わり、無事に第一志望の難関私立高校に合格。「私立高校の授業料無償化等に関する役所の対応について相談したい」というものでした。しかし、問題の根本をたどると、ミサさん母子が最低生活以下の生活を余儀なくされていたことがわかり、結果的に生活保護申請に行きつきました。
        ミサさんの「この時期、自分と同じように困っている母子家庭があると思うので、事例として公開してほしい」というたってのご希望から、生活保護申請に至った経緯と、そこから浮かび上がる「高校授業料無償化」の課題、そして行政の問題点について考えてみます。（行政書士・三木ひとみ）"""
        }
#         "title": "長期金利、一時1.5％台　国債の利回りが上昇し16年ぶりの高水準",
#         "content": """6日の東京債券市場で、長期金利の指標となる新発10年物国債の利回りが上昇（国債価格は下落）し、一時1・5％台を付けた。2009年6月以来、約16年ぶりの高水準となった。日銀が早期に追加利上げに動くとの観測が広がり、国債の売り圧力が強まっている。
# 　長期金利の上昇は、定期預金の金利や生命保険の利回りが増える効果がある一方、住宅ローンの借り手や融資を受ける企業の利払いの負担は大きくなる。【成澤隼人】"""
#     }
    
    # 分析用のテキストを準備
    analysis_text = f"\n記事:\nタイトル: {test_article['title']}\n本文:\n{test_article['content']}\n"
    
    # OpenAIアダプターの初期化
    openai = OpenaiAdapter()
    
    # 第1段階：初期分析
    initial_prompt = get_initial_article_analysis_prompt()
    logger.info("初期分析プロンプト:")
    logger.info(initial_prompt)
    
    logger.info("初期分析を実行中...")
    initial_response = openai.openai_chat(
        openai_model="gpt-4o",
        prompt=initial_prompt + "\n\n" + analysis_text
    )
    
    logger.info("初期分析の応答:")
    logger.info(initial_response)
    
    # 分析結果の解析
    initial_result = extract_tagged_json(initial_response, "analysis", logger)
    logger.info("解析された初期分析結果:")
    logger.info(json.dumps(initial_result, ensure_ascii=False, indent=2))
    
    # 第2段階：保険との関連性の再検証
    validation_prompt = get_relevance_validation_prompt().format(
        extracted_info=initial_result.get("extracted_info", ""),
        reasoning=initial_result.get("insurance_relevance", {}).get("reasoning", ""),
        conversation_example=initial_result.get("insurance_relevance", {}).get("conversation_example", "")
    )
    
    logger.info("検証プロンプト:")
    logger.info(validation_prompt)
    
    logger.info("検証を実行中...")
    validation_response = openai.openai_chat(
        openai_model="gpt-4o",
        prompt=validation_prompt
    )
    
    logger.info("検証の応答:")
    logger.info(validation_response)
    
    # 検証結果の解析
    validation_result = extract_tagged_json(validation_response, "validation", logger)
    logger.info("解析された検証結果:")
    logger.info(json.dumps(validation_result, ensure_ascii=False, indent=2))

def main():
    """メイン処理"""
    # 環境変数の読み込み
    load_dotenv()
    
    # ロガーの設定
    logger = setup_logging()
    logger.info("記事分析テストを開始します")
    
    # テスト用の記事データ
    test_article = {
        "title": "長期金利、一時1.5％台　国債の利回りが上昇し16年ぶりの高水準",
        "content": """6日の東京債券市場で、長期金利の指標となる新発10年物国債の利回りが上昇（国債価格は下落）し、一時1・5％台を付けた。2009年6月以来、約16年ぶりの高水準となった。日銀が早期に追加利上げに動くとの観測が広がり、国債の売り圧力が強まっている。
　長期金利の上昇は、定期預金の金利や生命保険の利回りが増える効果がある一方、住宅ローンの借り手や融資を受ける企業の利払いの負担は大きくなる。【成澤隼人】"""
    }
    
    logger.info("テスト記事:")
    logger.info(f"タイトル: {test_article['title']}")
    logger.info(f"内容: {test_article['content']}")
    
    # 記事分析の実行
    logger.info("記事分析を実行します...")
    analysis_result = analyze_individual_article_content(test_article, logger)
    
    # 結果の表示
    if analysis_result:
        logger.info("分析結果:")
        logger.info(f"本質情報あり: {analysis_result.get('has_essential_info', False)}")
        
        if analysis_result.get('has_essential_info', False):
            logger.info(f"抽出された情報: {analysis_result.get('extracted_info', '')}")
            logger.info(f"ターゲット顧客: {analysis_result.get('target_customers', '')}")
            logger.info(f"理由: {analysis_result.get('reasoning', '')}")
        else:
            logger.info(f"理由: {analysis_result.get('reasoning', '')}")
    else:
        logger.error("分析結果が取得できませんでした")
    
    # OpenAIの応答を直接確認するテスト
    logger.info("\n=== OpenAI応答の直接テスト ===\n")
    test_analyze_article_directly()

if __name__ == "__main__":
    main() 