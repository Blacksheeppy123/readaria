"""
用户听读队列与播放状态同步 - 数据库层单元测试
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime

from backend.storage.database import DatabaseManager


@pytest.fixture
def mock_db_manager():
    db = MagicMock(spec=DatabaseManager)
    db.pg_conn = MagicMock()
    db.logger = MagicMock()
    return db


@pytest.mark.unit
class TestUserQueue:
    """测试用户听读队列同步方法"""

    def test_get_user_queue_returns_items_and_updated_at(self, mock_db_manager):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            'items': [{'url': 'https://example.com/1', 'title': 'A'}],
            'updated_at': datetime(2026, 7, 15, 10, 0, 0)
        }
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.get_user_queue(mock_db_manager, 'user_123')

        assert result['items'] == [{'url': 'https://example.com/1', 'title': 'A'}]
        assert '2026-07-15T10:00:00' in result['updated_at']

    def test_get_user_queue_returns_empty_when_missing(self, mock_db_manager):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.get_user_queue(mock_db_manager, 'user_123')

        assert result['items'] == []
        assert result['updated_at'] is None

    def test_save_user_queue_upserts(self, mock_db_manager):
        cursor = MagicMock()
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        items = [{'url': 'https://example.com/1', 'title': 'A'}]
        ok = DatabaseManager.save_user_queue(mock_db_manager, 'user_123', items)

        assert ok is True
        sql = cursor.execute.call_args[0][0]
        assert 'INSERT INTO user_queues' in sql
        assert 'ON CONFLICT (user_id) DO UPDATE SET' in sql
        mock_db_manager.pg_conn.commit.assert_called_once()

    def test_clear_user_queue_deletes(self, mock_db_manager):
        cursor = MagicMock()
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        ok = DatabaseManager.clear_user_queue(mock_db_manager, 'user_123')

        assert ok is True
        sql = cursor.execute.call_args[0][0]
        assert 'DELETE FROM user_queues' in sql
        mock_db_manager.pg_conn.commit.assert_called_once()


@pytest.mark.unit
class TestPlaybackState:
    """测试用户播放状态同步方法"""

    def test_get_playback_state_returns_snapshot(self, mock_db_manager):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            'playlist': [{'url': 'https://example.com/1'}],
            'current_index': 2,
            'current_time': 12.5,
            'total_time': 120.0,
            'current_article': {'url': 'https://example.com/1', 'title': 'A'},
            'is_playing': True,
            'playback_rate': 1.25,
            'updated_at': datetime(2026, 7, 15, 10, 0, 0)
        }
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        result = DatabaseManager.get_playback_state(mock_db_manager, 'user_123')

        assert result['playlist'] == [{'url': 'https://example.com/1'}]
        assert result['current_index'] == 2
        assert result['current_time'] == 12.5
        assert result['total_time'] == 120.0
        assert result['current_article']['title'] == 'A'
        assert result['is_playing'] is True
        assert result['playback_rate'] == 1.25
        assert '2026-07-15T10:00:00' in result['updated_at']

    def test_save_playback_state_upserts(self, mock_db_manager):
        cursor = MagicMock()
        mock_db_manager.pg_conn.cursor.return_value.__enter__.return_value = cursor

        state = {
            'playlist': [{'url': 'https://example.com/1'}],
            'current_index': 1,
            'current_time': 10.0,
            'total_time': 100.0,
            'current_article': None,
            'is_playing': False,
            'playback_rate': 1.0
        }
        ok = DatabaseManager.save_playback_state(mock_db_manager, 'user_123', state)

        assert ok is True
        sql = cursor.execute.call_args[0][0]
        assert 'INSERT INTO user_playback_state' in sql
        assert 'ON CONFLICT (user_id) DO UPDATE SET' in sql
        mock_db_manager.pg_conn.commit.assert_called_once()
