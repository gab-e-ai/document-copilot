import html2text as _html2text


def html_to_markdown(html: str) -> str:
    h = _html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_tables = False
    h.body_width = 0  # don't hard-wrap lines
    h.unicode_snob = True
    return h.handle(html)
