"""DOCX from the shared layout with python-docx. ATS-friendly by construction: one column,
real paragraphs and Word's own heading and list styles, no tables, text boxes, or images, and
contact details in the body (some parsers skip headers and footers)."""

from __future__ import annotations

import io

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.styles.style import ParagraphStyle
from docx.text.paragraph import Paragraph as DocxParagraph

from rolehawk.rendering.layout import Bullets, CvLayout, Entry, LetterLayout, Paragraph
from rolehawk.rendering.templates import Paper, TemplateStyle

PAGE_SIZES = {"letter": (Inches(8.5), Inches(11)), "a4": (Inches(8.27), Inches(11.69))}
MUTED = RGBColor(0x37, 0x41, 0x51)


def _rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color.lstrip("#").upper())


def _set_font(style: ParagraphStyle, name: str, size: float, color: RGBColor | None = None) -> None:
    style.font.name = name
    style.font.size = Pt(size)
    if color is not None:
        style.font.color.rgb = color
    # East Asian text uses a separate font slot; keep it consistent.
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), name)
    # Built-in styles point at theme fonts, which Word prefers over the explicit name.
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        fonts.attrib.pop(qn(attr), None)
    for tag in ("w:spacing", "w:kern"):  # Title's letter-spacing and kerning
        for element in rpr.findall(qn(tag)):
            rpr.remove(element)


def _drop_borders(style: ParagraphStyle) -> None:
    ppr = style.element.get_or_add_pPr()
    for border in ppr.findall(qn("w:pBdr")):
        ppr.remove(border)


def _bottom_rule(paragraph: DocxParagraph, hex_color: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), hex_color.lstrip("#").upper())
    borders.append(bottom)
    ppr.append(borders)


class _Builder:
    def __init__(self, style: TemplateStyle, paper: Paper, title: str, author: str) -> None:
        self.s = style
        self.doc: DocxDocument = Document()
        section = self.doc.sections[0]
        section.page_width, section.page_height = PAGE_SIZES[paper]
        for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            setattr(section, side, Inches(style.margin_in))
        self.text_width = section.page_width - Inches(style.margin_in) * 2
        props = self.doc.core_properties
        props.title, props.author, props.comments = title, author, ""

        styles = self.doc.styles
        normal = styles["Normal"]
        assert isinstance(normal, ParagraphStyle)  # noqa: S101 - python-docx's built-in style
        _set_font(normal, style.font, style.body_pt)
        normal.paragraph_format.space_after = Pt(0)
        normal.paragraph_format.line_spacing = style.line_height
        accent = _rgb(style.accent)
        for name, size in (("Title", style.name_pt), ("Heading 1", style.heading_pt)):
            heading = styles[name]
            assert isinstance(heading, ParagraphStyle)  # noqa: S101
            _set_font(heading, style.font, size, accent)
            heading.font.bold = True
            heading.font.italic = False
            heading.paragraph_format.space_before = Pt(10 if name == "Heading 1" else 0)
            heading.paragraph_format.space_after = Pt(3)
            heading.paragraph_format.keep_with_next = True
            _drop_borders(heading)
        bullet = styles["List Bullet"]
        assert isinstance(bullet, ParagraphStyle)  # noqa: S101
        _set_font(bullet, style.font, style.body_pt)
        bullet.paragraph_format.space_after = Pt(1.5)
        if "RoleHawk Muted" not in [s.name for s in styles]:
            muted = styles.add_style("RoleHawk Muted", WD_STYLE_TYPE.PARAGRAPH)
            muted.base_style = normal
            muted.font.color.rgb = MUTED

    def masthead(self, name: str, lines: list[tuple[str, bool]]) -> None:
        title = self.doc.add_paragraph(name, style="Title")
        if self.s.name_align == "center":
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for text, muted in lines:
            p = self.doc.add_paragraph(text, style="RoleHawk Muted" if muted else "Normal")
            p.paragraph_format.space_before = Pt(2)
            if self.s.name_align == "center":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def heading(self, text: str) -> None:
        p = self.doc.add_paragraph(text, style="Heading 1")
        if self.s.heading_rule:
            _bottom_rule(p, self.s.accent)

    def paragraph(self, text: str, space_before: float = 0) -> DocxParagraph:
        p = self.doc.add_paragraph(text)
        p.paragraph_format.space_before = Pt(space_before)
        return p

    def entry(self, entry: Entry) -> None:
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(5)
        p.paragraph_format.keep_with_next = True
        p.add_run(entry.title).bold = True
        if entry.dates:
            p.paragraph_format.tab_stops.add_tab_stop(self.text_width, WD_TAB_ALIGNMENT.RIGHT)
            p.add_run("\t")
            p.add_run(entry.dates).font.color.rgb = MUTED
        if entry.subtitle:
            sub = self.doc.add_paragraph(style="RoleHawk Muted")
            sub.add_run(entry.subtitle).italic = True
        self.bullets(entry.bullets)

    def bullets(self, items: tuple[str, ...]) -> None:
        for item in items:
            self.doc.add_paragraph(item, style="List Bullet")

    def bytes(self) -> bytes:
        buffer = io.BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()


def cv_docx(layout: CvLayout, style: TemplateStyle, paper: Paper, title: str) -> bytes:
    b = _Builder(style, paper, title, layout.name)
    lines = [(layout.headline, False)] if layout.headline else []
    if layout.contact_text:
        lines.append((layout.contact_text, True))
    b.masthead(layout.name, lines)
    for section in layout.sections:
        b.heading(section.title)
        for block in section.blocks:
            if isinstance(block, Paragraph):
                b.paragraph(block.text)
            elif isinstance(block, Bullets):
                b.bullets(block.items)
            elif isinstance(block, Entry):
                b.entry(block)
    return b.bytes()


def letter_docx(layout: LetterLayout, style: TemplateStyle, paper: Paper, title: str) -> bytes:
    b = _Builder(style, paper, title, layout.name)
    b.masthead(layout.name, [(layout.contact_text, True)] if layout.contact_text else [])
    if layout.date:
        b.paragraph(layout.date, space_before=18)
    for i, line in enumerate(layout.recipient):
        b.paragraph(line, space_before=12 if i == 0 else 0)
    b.paragraph(layout.greeting, space_before=12)
    for text in layout.paragraphs:
        b.paragraph(text, space_before=10)
    b.paragraph(layout.closing, space_before=14)
    signature = b.paragraph("", space_before=24)
    signature.add_run(layout.signature).bold = True
    return b.bytes()
