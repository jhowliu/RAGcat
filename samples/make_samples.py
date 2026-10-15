"""Generate the demo PDFs in this folder.

    cd backend && uv run python ../samples/make_samples.py

- mochi-returns-policy.pdf: English, single column, running header, a ruled table, a bar chart.
- mochi-care-guide-zh.pdf: Traditional Chinese, a two-column page, a ruled table, a long paragraph.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
LEFT, RIGHT, TOP, BOTTOM = 72, 523, 72, 770


def header(doc: pymupdf.Document, title: str, fontname: str = "helv") -> None:
    for i, page in enumerate(doc, 1):
        page.insert_text((LEFT, 42), title, fontsize=8, fontname=fontname, color=(0.4, 0.4, 0.4))
        page.insert_text((RIGHT - 6, 42), str(i), fontsize=8, color=(0.4, 0.4, 0.4))


def ruled_table(page: pymupdf.Page, x: float, y: float, widths: list[float], rows: list[list[str]], fontname: str, size: float = 10) -> float:
    height = size * 2.2
    for r, row in enumerate(rows):
        cx = x
        for w, cell in zip(widths, row):
            rect = pymupdf.Rect(cx, y + r * height, cx + w, y + (r + 1) * height)
            page.draw_rect(rect, width=0.6)
            page.insert_text((cx + 5, y + r * height + size * 1.45), cell, fontsize=size, fontname="hebo" if r == 0 and fontname == "helv" else fontname)
            cx += w
    return y + len(rows) * height


def bar_chart(page: pymupdf.Page, x: float, y: float, bars: list[tuple[str, float]], unit: str) -> float:
    """A vector bar chart with value and axis labels; returns the y below it."""
    top, base, scale = y, y + 130, 110 / max(v for _, v in bars)
    page.draw_line((x, top), (x, base), width=0.8)
    page.draw_line((x, base), (x + 70 * len(bars) + 20, base), width=0.8)
    for i, (label, value) in enumerate(bars):
        left = x + 20 + i * 70
        page.draw_rect(pymupdf.Rect(left, base - value * scale, left + 40, base), color=(0.12, 0.24, 0.19), fill=(0.12, 0.24, 0.19))
        page.insert_text((left + 8, base - value * scale - 4), f"{value:g} {unit}", fontsize=8)
        page.insert_text((left, base + 12), label, fontsize=8)
    return base + 20


def cjk_paragraph(page: pymupdf.Page, x: float, y: float, width: float, text: str, size: float = 10.5, fontname: str = "china-t") -> float:
    """Insert CJK text wrapped by character count (insert_textbox only wraps at spaces)."""
    per_line = int(width // size)
    for start in range(0, len(text), per_line):
        y += size * 1.6
        page.insert_text((x, y), text[start : start + per_line], fontsize=size, fontname=fontname)
    return y + size * 1.2


def english() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    y = TOP

    def write(text: str, size: float = 11, bold: bool = False) -> None:
        nonlocal y
        height = (len(text) // 85 + 1) * size * 1.45 + 6
        page.insert_textbox(pymupdf.Rect(LEFT, y, RIGHT, y + height), text, fontsize=size, fontname="hebo" if bold else "helv")
        y += height + (6 if bold else size)

    write("Mochi Pet Co. · Returns policy", 20, True)
    write("1. Who can return", 14, True)
    write("Orders placed on mochipet.example can be returned by the original buyer within 30 days of delivery. Gift recipients can ask for store credit instead of a refund, using the order number printed on the gift receipt.")
    write("2. Opened items", 14, True)
    write("Opened items cannot be returned unless the item is defective. A defective item arrives damaged, spoiled, or different from the listing. Send a photo of the item and the packaging so our team can confirm the problem.")
    write("3. How to start a return", 14, True)
    write("To request a return, contact support within 7 days with your order number and a photo of the item and its packaging. We reply within 2 business days with a prepaid label for eligible returns. Refunds go back to the original payment method within 5 business days after the parcel arrives.")
    write("4. Shipping times", 14, True)
    write("Orders ship within two business days. Standard shipping takes three to five business days within Australia. Express shipping arrives the next business day in metro areas and two days elsewhere.")

    page = doc.new_page()
    y = TOP
    write("Delivery fees", 14, True)
    y = ruled_table(page, LEFT, y, [150, 120, 120], [["Region", "Standard", "Express"], ["Metro", "$9.95", "$14.95"], ["Regional", "$12.95", "$19.95"], ["Remote", "$18.95", "$29.95"]], "helv") + 14
    write("Orders over $89 ship free with standard shipping. Express shipping is always charged at the rates above.")
    y = bar_chart(page, LEFT + 10, y, [("Metro", 2.5), ("Regional", 4), ("Remote", 7.5)], "days")
    write("Figure 1. Average standard delivery time by region, last quarter", 9)
    write("5. Food storage", 14, True)
    write("Store kibble in a cool, dry place and keep the bag sealed after opening. Use opened bags within six weeks so the food stays fresh. Wet food should be refrigerated after opening and used within three days.")
    write("6. Contact", 14, True)
    write("Email help@mochipet.example or call 1300 664 244 between 9am and 5pm AEST, Monday to Friday.")
    header(doc, "Mochi Pet Co. · Returns policy")
    doc.save(HERE / "mochi-returns-policy.pdf")


def chinese() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((LEFT, 86), "Mochi 毛孩照護指南", fontsize=20, fontname="china-t")
    columns = {
        LEFT: [
            ("一、每日餵食", 13),
            ("成犬每天餵食兩次，早晚各一次，間隔約十二小時。幼犬消化系統較弱，建議少量多餐，每天分三到四次餵食。換新飼料時，請用七天逐步混合新舊飼料，避免腸胃不適。", 10.5),
            ("二、飲水", 13),
            ("隨時提供乾淨的飲用水，並每天更換。夏天或運動後飲水量會增加，外出時記得攜帶水壺。", 10.5),
        ],
        312: [
            ("三、飼料保存", 13),
            ("乾飼料開封後請將袋口密封，存放在陰涼乾燥處，並在六週內食用完畢。濕食開封後需冷藏，並於三天內食用。", 10.5),
            ("四、零食", 13),
            ("零食熱量不應超過每日總熱量的一成。巧克力、葡萄、洋蔥對狗狗有毒，請勿餵食。", 10.5),
        ],
    }
    for x, items in columns.items():
        y = 110
        for text, size in items:
            y = cjk_paragraph(page, x, y, 210, text, size)
    page.insert_text((LEFT, 430), "餵食份量參考", fontsize=13, fontname="china-t")
    ruled_table(page, LEFT, 445, [130, 130, 130], [["體重", "每日乾飼料", "每日飲水"], ["5 公斤", "80 公克", "350 毫升"], ["10 公斤", "140 公克", "600 毫升"], ["20 公斤", "240 公克", "1,100 毫升"]], "china-t")

    page = doc.new_page()
    page.insert_text((LEFT, 86), "五、退換貨說明", fontsize=13, fontname="china-t")
    long_text = (
        "未開封的商品可以在收到後三十天內退貨並全額退款。已開封的商品除非有瑕疵，否則不接受退貨；所謂瑕疵是指商品送達時已損壞、變質，或與商品頁面描述不符。"
        "申請退貨時，請在收到商品後七天內聯絡客服，並提供訂單編號以及商品與包裝的照片。客服會在兩個工作天內回覆，符合資格的退貨會附上預付運單。"
        "退款會在包裹送達後五個工作天內退回原付款方式。若您收到的是禮物，可以憑禮物收據上的訂單編號申請購物金，而不是退款。"
        "大型商品如貓跳台、狗屋等，退貨運費由買家負擔，除非商品本身有瑕疵。特價商品與客製化商品恕不退換。"
        "如有任何問題，請寫信至 help@mochipet.example，或於週一至週五上午九點到下午五點來電 1300 664 244。"
    )
    cjk_paragraph(page, LEFT, 100, RIGHT - LEFT, long_text)
    header(doc, "Mochi 毛孩照護指南", fontname="china-t")
    doc.save(HERE / "mochi-care-guide-zh.pdf")


if __name__ == "__main__":
    english()
    chinese()
    print("wrote", *(p.name for p in sorted(HERE.glob("*.pdf"))))
