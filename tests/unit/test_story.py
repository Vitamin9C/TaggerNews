"""Unit tests for Story domain entity."""



from taggernews.domain.story import Story


class TestStory:
    """Tests for Story domain entity."""

    def test_from_hn_api_complete_data(self):
        """Test creating Story from complete HN API response."""
        data = {
            "id": 12345,
            "title": "Test Story Title",
            "url": "https://example.com/story",
            "score": 100,
            "by": "testuser",
            "descendants": 50,
            "time": 1700000000,
            "type": "story",
        }

        story = Story.from_hn_api(data)

        assert story.hn_id == 12345
        assert story.title == "Test Story Title"
        assert story.url == "https://example.com/story"
        assert story.score == 100
        assert story.author == "testuser"
        assert story.comment_count == 50
        assert story.id is None  # Not yet persisted

    def test_from_hn_api_minimal_data(self):
        """Test creating Story from minimal HN API response."""
        data = {
            "id": 12345,
            "type": "story",
        }

        story = Story.from_hn_api(data)

        assert story.hn_id == 12345
        assert story.title == ""
        assert story.url is None
        assert story.score == 0
        assert story.author == "unknown"
        assert story.comment_count == 0

    def test_from_hn_api_ask_hn_no_url(self):
        """Test creating Story from Ask HN post (no URL)."""
        data = {
            "id": 12345,
            "title": "Ask HN: What's your favorite editor?",
            "score": 50,
            "by": "curious",
            "descendants": 200,
            "time": 1700000000,
            "type": "story",
        }

        story = Story.from_hn_api(data)

        assert story.url is None
        assert "Ask HN" in story.title
