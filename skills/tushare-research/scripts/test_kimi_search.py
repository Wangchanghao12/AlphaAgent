#!/usr/bin/env python3
"""
Kimi Search 模块单元测试
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kimi_search import (
    moonshot_search,
    brave_search,
    duckduckgo_search,
    searxng_search,
    kimi_search
)


def check_duckduckgo_installed():
    """检查 duckduckgo-search 是否已安装"""
    try:
        import duckduckgo_search
        return True
    except ImportError:
        return False


class TestMoonshotSearch(unittest.TestCase):
    """测试 Moonshot API 搜索"""
    
    @patch.dict(os.environ, {'MOONSHOT_API_KEY': 'test-key'}, clear=False)
    @patch('kimi_search.requests.post')
    def test_moonshot_search_success(self, mock_post):
        """测试成功返回搜索结果"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps([
                        {"title": "测试标题", "url": "https://example.com", "snippet": "测试摘要"}
                    ])
                }
            }]
        }
        mock_post.return_value = mock_response
        
        results = moonshot_search("测试查询", limit=5)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], "测试标题")
        self.assertEqual(results[0]['url'], "https://example.com")
        self.assertEqual(results[0]['snippet'], "测试摘要")
    
    @patch.dict(os.environ, {'MOONSHOT_API_KEY': ''}, clear=False)
    def test_moonshot_no_api_key(self):
        """测试无 API Key 时返回空列表"""
        results = moonshot_search("测试")
        self.assertEqual(results, [])
    
    @patch.dict(os.environ, {'MOONSHOT_API_KEY': 'test-key'}, clear=False)
    @patch('kimi_search.requests.post')
    def test_moonshot_api_error(self, mock_post):
        """测试 API 错误时返回空列表"""
        mock_post.side_effect = Exception("Network error")
        
        results = moonshot_search("测试")
        self.assertEqual(results, [])
    
    @patch.dict(os.environ, {'MOONSHOT_API_KEY': 'test-key'}, clear=False)
    @patch('kimi_search.requests.post')
    def test_moonshot_invalid_json(self, mock_post):
        """测试返回非 JSON 格式时的降级处理"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '这不是有效的JSON'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        results = moonshot_search("测试")
        
        # 应该返回降级结果
        self.assertEqual(len(results), 1)
        self.assertIn('搜索：', results[0]['title'])


class TestBraveSearch(unittest.TestCase):
    """测试 Brave Search API"""
    
    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-brave-key'}, clear=False)
    @patch('kimi_search.requests.get')
    def test_brave_search_success(self, mock_get):
        """测试成功返回搜索结果"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'web': {
                'results': [
                    {
                        'title': 'Brave搜索结果',
                        'url': 'https://brave.com',
                        'description': 'Brave描述'
                    }
                ]
            }
        }
        mock_get.return_value = mock_response
        
        results = brave_search("测试", limit=5)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Brave搜索结果')
    
    @patch.dict(os.environ, {'BRAVE_API_KEY': ''}, clear=False)
    def test_brave_no_api_key(self):
        """测试无 API Key 时返回空列表"""
        results = brave_search("测试")
        self.assertEqual(results, [])


class TestDuckDuckGoSearch(unittest.TestCase):
    """测试 DuckDuckGo 搜索"""
    
    @unittest.skipUnless(check_duckduckgo_installed(), "duckduckgo-search 未安装")
    @patch('duckduckgo_search.DDGS')
    def test_duckduckgo_search_success(self, mock_ddgs_class):
        """测试成功返回搜索结果"""
        mock_ddgs_instance = MagicMock()
        mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.return_value = [
            {'title': 'DDG结果', 'href': 'https://ddg.com', 'body': 'DDG描述'}
        ]
        
        results = duckduckgo_search("测试", limit=5)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'DDG结果')
        self.assertEqual(results[0]['url'], 'https://ddg.com')
    
    @unittest.skipUnless(check_duckduckgo_installed(), "duckduckgo-search 未安装")
    @patch('duckduckgo_search.DDGS')
    def test_duckduckgo_search_error(self, mock_ddgs_class):
        """测试搜索失败时返回空列表"""
        mock_ddgs_class.side_effect = Exception("DDG Error")
        
        results = duckduckgo_search("测试")
        self.assertEqual(results, [])


class TestSearXNGSearch(unittest.TestCase):
    """测试 SearXNG 搜索"""
    
    @patch.dict(os.environ, {'SEARXNG_URL': 'https://searx.example.com'}, clear=False)
    @patch('kimi_search.requests.get')
    def test_searxng_search_success(self, mock_get):
        """测试成功返回搜索结果"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'results': [
                {'title': 'SearXNG结果', 'url': 'https://searx.org', 'content': 'SearXNG描述'}
            ]
        }
        mock_get.return_value = mock_response
        
        results = searxng_search("测试", limit=5)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'SearXNG结果')
    
    @patch.dict(os.environ, {'SEARXNG_URL': ''}, clear=False)
    def test_searxng_no_url(self):
        """测试无 URL 时返回空列表"""
        results = searxng_search("测试")
        self.assertEqual(results, [])


class TestKimiSearch(unittest.TestCase):
    """测试主搜索函数（多后端自动降级）"""
    
    @patch('kimi_search.moonshot_search')
    def test_kimi_search_fallback(self, mock_moonshot):
        """测试后端降级：Moonshot 失败时使用其他后端"""
        # Moonshot 返回空，模拟失败
        mock_moonshot.return_value = []
        
        with patch('kimi_search.brave_search') as mock_brave:
            mock_brave.return_value = [{'title': 'Brave结果', 'url': '#', 'snippet': ''}]
            
            results = kimi_search("测试")
            
            mock_moonshot.assert_called_once()
            mock_brave.assert_called_once()
            self.assertEqual(results[0]['title'], 'Brave结果')
    
    @patch('kimi_search.moonshot_search')
    @patch('kimi_search.brave_search')
    @patch('kimi_search.duckduckgo_search')
    def test_kimi_search_all_fail(self, mock_ddg, mock_brave, mock_moonshot):
        """测试所有后端都失败时返回空列表"""
        mock_moonshot.return_value = []
        mock_brave.return_value = []
        mock_ddg.return_value = []
        
        results = kimi_search("测试")
        
        self.assertEqual(results, [])
    
    @patch('kimi_search.moonshot_search')
    def test_kimi_search_include_content(self, mock_moonshot):
        """测试 include_content 参数"""
        mock_moonshot.return_value = [
            {'title': '结果', 'url': 'https://example.com', 'snippet': '摘要内容'}
        ]
        
        results = kimi_search("测试", include_content=True)
        
        self.assertIn('content', results[0])
        self.assertEqual(results[0]['content'], '摘要内容')
    
    @patch('kimi_search.moonshot_search')
    def test_kimi_search_limit(self, mock_moonshot):
        """测试 limit 参数传递给后端"""
        mock_moonshot.return_value = [
            {'title': f'结果{i}', 'url': f'https://example.com/{i}', 'snippet': ''}
            for i in range(10)
        ]
        
        results = kimi_search("测试", limit=3)
        
        # 验证 limit 参数被传递给后端
        mock_moonshot.assert_called_once_with("测试", 3)
        # 返回后端返回的所有结果（不做额外截断）
        self.assertEqual(len(results), 10)


class TestEdgeCases(unittest.TestCase):
    """边界情况测试"""
    
    @patch('kimi_search.moonshot_search')
    def test_empty_query(self, mock_moonshot):
        """测试空查询"""
        mock_moonshot.return_value = []
        mock_moonshot.return_value = [{'title': '结果', 'url': '#', 'snippet': ''}]
        
        results = kimi_search("")
        
        mock_moonshot.assert_called_once()
    
    @patch('kimi_search.moonshot_search')
    def test_special_characters(self, mock_moonshot):
        """测试特殊字符"""
        mock_moonshot.return_value = [{'title': '结果', 'url': '#', 'snippet': ''}]
        
        results = kimi_search("测试 <>&\"' 特殊字符")
        
        mock_moonshot.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
