"""Tests for utility functions."""

import pytest

from sysupdate.utils import command_available


class TestCommandAvailable:
    """Tests for command_available function."""

    @pytest.mark.asyncio
    async def test_available_command(self):
        """Test that available commands return True."""
        result = await command_available("which", "ls")
        assert result is True

    @pytest.mark.asyncio
    async def test_unavailable_command(self):
        """Test that unavailable commands return False."""
        result = await command_available("nonexistent_command_12345")
        assert result is False

    @pytest.mark.asyncio
    async def test_caching_works(self):
        """Test that results are cached and reused."""
        # Import the cache directly to inspect it
        from sysupdate.utils import _availability_cache

        # Clear cache before test
        _availability_cache.clear()

        # First call - should execute and cache
        result1 = await command_available("which", "ls")
        assert result1 is True
        assert ("which", ("ls",)) in _availability_cache

        # Second call - should use cache
        result2 = await command_available("which", "ls")
        assert result2 is True
        assert result1 == result2

        # Cache should still have only one entry
        assert len(_availability_cache) == 1

    @pytest.mark.asyncio
    async def test_different_commands_cached_separately(self):
        """Test that different commands are cached separately."""
        from sysupdate.utils import _availability_cache

        _availability_cache.clear()

        # Test two different commands
        result1 = await command_available("which", "ls")
        result2 = await command_available("which", "cat")

        assert result1 is True
        assert result2 is True

        # Both should be cached
        assert ("which", ("ls",)) in _availability_cache
        assert ("which", ("cat",)) in _availability_cache
        assert len(_availability_cache) == 2

    @pytest.mark.asyncio
    async def test_different_args_cached_separately(self):
        """Test that same command with different args are cached separately."""
        from sysupdate.utils import _availability_cache

        _availability_cache.clear()

        # Test same command with different arguments
        result1 = await command_available("test", "-f", "/bin/ls")
        result2 = await command_available("test", "-d", "/tmp")

        # Both should be in cache with different keys
        assert ("test", ("-f", "/bin/ls")) in _availability_cache
        assert ("test", ("-d", "/tmp")) in _availability_cache
        assert len(_availability_cache) == 2

    @pytest.mark.asyncio
    async def test_cache_negative_results(self):
        """Test that negative results are also cached."""
        from sysupdate.utils import _availability_cache

        _availability_cache.clear()

        # First call to non-existent command
        result1 = await command_available("nonexistent_command_99999")
        assert result1 is False

        # Should be in cache
        assert ("nonexistent_command_99999", ()) in _availability_cache

        # Second call should use cache
        result2 = await command_available("nonexistent_command_99999")
        assert result2 is False
        assert result1 == result2
