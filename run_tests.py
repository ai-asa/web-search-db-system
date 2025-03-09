import unittest
import sys
import os

def run_tests():
    """テストを実行する関数"""
    # テストディレクトリをPythonパスに追加
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)
    
    # テストを検出して実行
    test_suite = unittest.defaultTestLoader.discover(
        start_dir=current_dir,
        pattern='test_*.py'
    )
    
    # テスト結果を表示
    test_runner = unittest.TextTestRunner(verbosity=2)
    result = test_runner.run(test_suite)
    
    # 終了コードを設定（テストが失敗した場合は1、成功した場合は0）
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    sys.exit(run_tests()) 