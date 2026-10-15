from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pymupdf
import pytest

DYNAMODB = os.environ.get("RAGCAT_TEST_DYNAMODB", "http://localhost:8001")


def pytest_addoption(parser) -> None:
    parser.addoption("--require-integration", action="store_true", help="Fail instead of skipping when DynamoDB Local is unavailable")


@pytest.fixture(scope="session")
def dynamodb_endpoint(request) -> str:
    url = urlparse(DYNAMODB)
    try:
        socket.create_connection((url.hostname, url.port), timeout=1).close()
    except OSError:
        if request.config.getoption("--require-integration"):
            pytest.fail(f"DynamoDB Local is required at {DYNAMODB}; run docker compose up -d dynamodb")
        pytest.skip(f"DynamoDB Local is not running at {DYNAMODB} (docker compose up -d dynamodb)")
    return DYNAMODB


def make_pdf(pages: list[list[tuple[str, float, bool]]]) -> bytes:
    """Build a PDF where each page is a list of (text, font size, bold) paragraphs."""
    doc = pymupdf.open()
    for paragraphs in pages:
        page = doc.new_page()
        y = 72.0
        for text, size, bold in paragraphs:
            height = (len(text) // 80 + 1) * size * 1.4 + 6
            page.insert_textbox(pymupdf.Rect(72, y, 523, y + height), text, fontsize=size, fontname="hebo" if bold else "helv")
            y += height + size
    data = doc.tobytes()
    doc.close()
    return data


RETURNS_PDF_PAGES = [
    [
        ("Returns policy", 18, True),
        (
            "Unopened items can be returned within 30 days of delivery for a full refund. "
            "Opened items cannot be returned unless the item is defective. "
            "Contact support with your order number to start a return.",
            11,
            False,
        ),
        ("Shipping", 18, True),
        (
            "Orders ship within two business days. Standard shipping takes three to five days "
            "within Australia, and express shipping arrives the next business day in metro areas.",
            11,
            False,
        ),
    ],
    [
        ("Pet food storage", 18, True),
        (
            "Store kibble in a cool, dry place and keep the bag sealed after opening. "
            "Use opened bags within six weeks so the food stays fresh for your pet.",
            11,
            False,
        ),
    ],
]


def make_figure_pdf() -> bytes:
    """Two pages: a repeated small logo on each; page 1 has a photo, a vector bar chart with
    labels and a caption, and a paragraph."""
    doc = pymupdf.open()
    logo = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    logo.set_rect(logo.irect, (30, 60, 50))
    photo = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 180), False)
    photo.set_rect(photo.irect, (200, 120, 60))
    for n in range(2):
        page = doc.new_page()
        page.insert_image(pymupdf.Rect(500, 20, 530, 50), pixmap=logo)
        if n == 0:
            page.insert_text((72, 80), "Delivery report", fontsize=18, fontname="hebo")
            page.insert_image(pymupdf.Rect(72, 100, 372, 280), pixmap=photo)
            for i, (label, h) in enumerate([("Metro", 40), ("Regional", 80), ("Remote", 110)]):
                x = 110 + i * 70
                page.draw_rect(pymupdf.Rect(x, 460 - h, x + 40, 460), color=(0, 0, 0), fill=(0.2, 0.4, 0.6))
                page.insert_text((x, 472), label, fontsize=8)
            page.draw_line((96, 460), (330, 460))
            page.draw_line((96, 330), (96, 460))
            page.insert_text((72, 495), "Figure 1. Average delivery days by region", fontsize=9)
            page.insert_textbox(pymupdf.Rect(72, 520, 523, 600), "Remote deliveries take the longest because parcels travel by road freight from the nearest hub.", fontsize=11)
        else:
            page.insert_textbox(pymupdf.Rect(72, 80, 523, 160), "Page two only has text about returns and refunds for every order.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data
