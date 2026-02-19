"""Edge case tests for tag taxonomy: empty tags, duplicates, special chars, long names."""

import pytest

from taggernews.services.tag_taxonomy import (
    FlatTags,
    TaxonomyService,
    get_category_for_tag,
    get_level_for_tag,
    normalize_slug,
)


class TestNormalizeSlugEdgeCases:
    """Additional edge cases for normalize_slug."""

    def test_empty_string(self):
        assert normalize_slug("") == ""

    def test_only_special_chars(self):
        """String of only special chars produces empty slug."""
        assert normalize_slug("!@#$%^&*()") == ""

    def test_only_hyphens(self):
        assert normalize_slug("---") == ""

    def test_only_spaces(self):
        assert normalize_slug("   ") == ""

    def test_numbers_preserved(self):
        assert normalize_slug("Python3") == "python3"

    def test_mixed_separators(self):
        assert normalize_slug("hello_world test") == "hello-world-test"

    def test_consecutive_special_chars(self):
        """Multiple consecutive special chars collapse to single hyphen."""
        assert normalize_slug("foo!!!bar") == "foo-bar"

    def test_very_long_name(self):
        """Very long tag names get slugified without error."""
        long_name = "A" * 1000
        result = normalize_slug(long_name)
        assert result == "a" * 1000

    def test_leading_trailing_special_chars(self):
        assert normalize_slug("!!Python!!") == "python"

    def test_slash_becomes_hyphen(self):
        assert normalize_slug("AI/ML") == "ai-ml"

    def test_dot_becomes_hyphen(self):
        assert normalize_slug("node.js") == "node-js"

    def test_plus_stripped(self):
        """Plus signs are stripped (non-alphanumeric)."""
        result = normalize_slug("C++")
        assert result == "c"

    def test_ampersand_becomes_hyphen(self):
        assert normalize_slug("R&D") == "r-d"


class TestGetLevelForTagEdgeCases:
    """Edge cases for get_level_for_tag."""

    def test_case_sensitive_l1(self):
        """L1 lookup is case-sensitive."""
        assert get_level_for_tag("tech") == 3  # "tech" != "Tech"
        assert get_level_for_tag("TECH") == 3

    def test_case_sensitive_l2(self):
        """L2 lookup is case-sensitive."""
        assert get_level_for_tag("ai/ml") == 3  # "ai/ml" != "AI/ML"

    def test_empty_string(self):
        """Empty string defaults to L3."""
        assert get_level_for_tag("") == 3

    def test_whitespace(self):
        """Whitespace string defaults to L3."""
        assert get_level_for_tag("  ") == 3

    def test_all_l1_tags(self):
        """Verify all canonical L1 tags are recognized."""
        for tag in ["Tech", "Business", "Science", "Society"]:
            assert get_level_for_tag(tag) == 1

    def test_all_region_l2_tags(self):
        """Verify region L2 tags."""
        for tag in ["EU", "USA", "China", "Canada", "India", "Germany", "France", "Netherlands", "UK"]:
            assert get_level_for_tag(tag) == 2


class TestGetCategoryForTagEdgeCases:
    """Edge cases for get_category_for_tag."""

    def test_l1_tag_has_no_category(self):
        """L1 tags don't have categories."""
        for tag in ["Tech", "Business", "Science", "Society"]:
            assert get_category_for_tag(tag) is None

    def test_l3_tag_has_no_category(self):
        """Unknown/L3 tags return None."""
        assert get_category_for_tag("GPT-4") is None

    def test_empty_string(self):
        assert get_category_for_tag("") is None

    def test_all_categories_consistent(self):
        """Every L2 tag with a category returns a known category name."""
        known_categories = {"Region", "Tech Stacks", "Tech Topics", "Business", "Science"}
        from taggernews.services.tag_taxonomy import L2_TAG_CATEGORIES

        for tag_name, category in L2_TAG_CATEGORIES.items():
            assert category in known_categories, f"{tag_name} has unknown category: {category}"


class TestFlatTagsEdgeCases:
    """Edge cases for FlatTags dataclass."""

    def test_duplicate_tags_preserved(self):
        """FlatTags does not deduplicate."""
        tags = FlatTags(l1_tags=["Tech", "Tech"])
        assert tags.all_tags() == ["Tech", "Tech"]

    def test_empty_string_tags(self):
        """Empty string tags are preserved."""
        tags = FlatTags(l1_tags=[""], l2_tags=[""])
        assert tags.all_tags() == ["", ""]

    def test_order_is_l1_l2_l3(self):
        """all_tags always returns l1 first, then l2, then l3."""
        tags = FlatTags(
            l1_tags=["Society"],
            l2_tags=["AI/ML"],
            l3_tags=["OpenAI"],
        )
        result = tags.all_tags()
        assert result == ["Society", "AI/ML", "OpenAI"]

    def test_many_tags(self):
        """FlatTags handles large number of tags."""
        tags = FlatTags(
            l1_tags=["Tech"] * 10,
            l2_tags=["AI/ML"] * 50,
            l3_tags=["OpenAI"] * 100,
        )
        assert len(tags.all_tags()) == 160


class TestTaxonomyServiceResolve:
    """Tests for TaxonomyService.resolve_tags deduplication."""

    @pytest.mark.asyncio
    async def test_deduplicates_by_slug(self):
        """resolve_tags skips tags that normalize to the same slug."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = AsyncMock()
        service = TaxonomyService(mock_session)

        mock_tag = MagicMock()
        service.get_or_create_tag = AsyncMock(return_value=mock_tag)

        # "AI/ML" and "ai/ml" both normalize to "ai-ml"
        flat_tags = FlatTags(l2_tags=["AI/ML", "ai/ml"])
        result = await service.resolve_tags(flat_tags)

        # Should only create/get one tag
        assert service.get_or_create_tag.call_count == 1
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_empty_flat_tags(self):
        """resolve_tags with empty FlatTags returns empty list."""
        from unittest.mock import AsyncMock

        mock_session = AsyncMock()
        service = TaxonomyService(mock_session)

        result = await service.resolve_tags(FlatTags())
        assert result == []

    @pytest.mark.asyncio
    async def test_preserves_order_after_dedup(self):
        """resolve_tags returns tags in the order they first appear."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = AsyncMock()
        service = TaxonomyService(mock_session)

        call_order = []

        async def mock_get_or_create(name):
            call_order.append(name)
            tag = MagicMock()
            tag.name = name
            return tag

        service.get_or_create_tag = mock_get_or_create

        flat_tags = FlatTags(
            l1_tags=["Tech"],
            l2_tags=["AI/ML", "Web"],
            l3_tags=["OpenAI"],
        )
        result = await service.resolve_tags(flat_tags)

        assert len(result) == 4
        assert call_order == ["Tech", "AI/ML", "Web", "OpenAI"]
