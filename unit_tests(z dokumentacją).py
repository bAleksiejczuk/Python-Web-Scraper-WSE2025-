"""Testy jednostkowe (pytest) dla projektu Web Crawler + Ekstraktor Tekstu.

Zakres testów jest celowo niewielki i obejmuje kluczowe elementy logiki
pomocniczej, które powinny działać deterministycznie:
  - normalizacja URL w Config (dodanie schematu https://),
  - weryfikacja dozwolonych domen w DomainManager,
  - poprawność ekstrakcji tekstu z HTML w HTMLParser.

Testy są spójne z dokumentacją projektową i mają charakter regresyjny —
umożliwiają szybkie wykrycie niezamierzonych zmian w zachowaniu programu.
"""

import pytest

from app import Config, DomainManager, HTMLParser


# =========================
# TEST 1: Config.normalize_url
# =========================
def test_config_normalize_url_adds_https():
    """Sprawdza, czy brakujący schemat URL jest uzupełniany do https://."""
    config = Config(url="example.com")
    config.normalize_url()

    assert config.url == "https://example.com"


# =========================
# TEST 2: DomainManager.is_allowed
# =========================
def test_domain_manager_allows_same_domain_and_www():
    """Sprawdza, czy DomainManager akceptuje domenę z i bez prefiksu www."""
    dm = DomainManager("https://example.com")

    assert dm.is_allowed("example.com") is True
    assert dm.is_allowed("www.example.com") is True
    assert dm.is_allowed("google.com") is False


# =========================
# TEST 3: HTMLParser._extract_text
# =========================
def test_html_parser_extract_text_removes_scripts_and_keeps_content():
    """Sprawdza, czy ekstrakcja tekstu usuwa elementy <script> i zachowuje treść."""
    dm = DomainManager("https://example.com")
    parser = HTMLParser(dm)

    html = """
    <html>
        <head>
            <title>Test</title>
            <script>alert("x")</script>
        </head>
        <body>
            <h1>Nagłówek</h1>
            <p>Paragraf</p>
            <ul>
                <li>Element 1</li>
                <li>Element 2</li>
            </ul>
        </body>
    </html>
    """

    text = parser._extract_text(parser=parser, soup=None) if False else parser._extract_text(
        __import__("bs4").BeautifulSoup(html, "html.parser")
    )

    assert "alert" not in text
    assert "Nagłówek" in text
    assert "Paragraf" in text
    assert "• Element 1" in text
