"""Tests for tag taxonomy functions and TagFilter."""

from taggernews.repositories.story_repo import TagFilter
from taggernews.services.tag_taxonomy import (
    FlatTags,
    get_category_for_tag,
    get_level_for_tag,
    normalize_slug,
)


class TestNormalizeSlug:
    """Tests for normalize_slug."""

    def test_lowercase(self):
        assert normalize_slug("AI/ML") == "ai-ml"

    def test_spaces(self):
        assert normalize_slug("Open Source") == "open-source"

    def test_special_chars(self):
        assert normalize_slug("C++") == "c"

    def test_strip_hyphens(self):
        assert normalize_slug("--hello--") == "hello"

    def test_multiple_special_chars(self):
        assert normalize_slug("foo & bar!") == "foo-bar"

    def test_whitespace_trim(self):
        assert normalize_slug("  Python  ") == "python"

    def test_unicode(self):
        # Non-ASCII chars get stripped to hyphens
        result = normalize_slug("café")
        assert result == "caf"


class TestGetLevelForTag:
    """Tests for get_level_for_tag."""

    def test_l1_tags(self):
        assert get_level_for_tag("Tech") == 1
        assert get_level_for_tag("Business") == 1
        assert get_level_for_tag("Science") == 1
        assert get_level_for_tag("Society") == 1

    def test_l2_tags(self):
        assert get_level_for_tag("AI/ML") == 2
        assert get_level_for_tag("Python") == 2
        assert get_level_for_tag("Startups") == 2
        assert get_level_for_tag("USA") == 2

    def test_unknown_defaults_to_l3(self):
        assert get_level_for_tag("OpenAI") == 3
        assert get_level_for_tag("SomeRandomTag") == 3


class TestGetCategoryForTag:
    """Tests for get_category_for_tag."""

    def test_known_category(self):
        assert get_category_for_tag("Python") == "Tech Stacks"
        assert get_category_for_tag("AI/ML") == "Tech Topics"
        assert get_category_for_tag("USA") == "Region"
        assert get_category_for_tag("Startups") == "Business"
        assert get_category_for_tag("Research") == "Science"

    def test_unknown_returns_none(self):
        assert get_category_for_tag("OpenAI") is None
        assert get_category_for_tag("Tech") is None


class TestFlatTags:
    """Tests for FlatTags dataclass."""

    def test_all_tags_combines_levels(self):
        tags = FlatTags(
            l1_tags=["Tech"],
            l2_tags=["AI/ML", "Python"],
            l3_tags=["OpenAI"],
        )
        assert tags.all_tags() == ["Tech", "AI/ML", "Python", "OpenAI"]

    def test_all_tags_empty(self):
        tags = FlatTags()
        assert tags.all_tags() == []

    def test_all_tags_partial(self):
        tags = FlatTags(l2_tags=["Web"])
        assert tags.all_tags() == ["Web"]


class TestTagFilter:
    """Tests for TagFilter dataclass."""

    def test_is_empty_when_empty(self):
        assert TagFilter().is_empty() is True

    def test_is_empty_with_l1_include(self):
        assert TagFilter(l1_include=["Tech"]).is_empty() is False

    def test_is_empty_with_l2_exclude(self):
        assert TagFilter(l2_exclude=["Finance"]).is_empty() is False

    def test_is_empty_with_l3_include(self):
        assert TagFilter(l3_include=["OpenAI"]).is_empty() is False
