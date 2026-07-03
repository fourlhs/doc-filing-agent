"""Tests for the DocumentContent side of the contract."""

import pytest

from agent.schema import DocumentContent


@pytest.mark.parametrize(
    "content",
    [
        DocumentContent(),
        DocumentContent(text=None),
        DocumentContent(text=""),
        DocumentContent(text="   \n\t "),
    ],
    ids=["default", "none-text", "empty-text", "whitespace-text"],
)
def test_is_empty_when_nothing_usable(content):
    assert content.is_empty


@pytest.mark.parametrize(
    "content",
    [
        DocumentContent(text="ΤΙΜΟΛΟΓΙΟ"),
        DocumentContent(pages=[b"\x89PNG fake bytes"]),
        DocumentContent(text="", pages=[b"\x89PNG fake bytes"]),
    ],
    ids=["text", "pages", "empty-text-with-pages"],
)
def test_not_empty_with_usable_content(content):
    assert not content.is_empty
