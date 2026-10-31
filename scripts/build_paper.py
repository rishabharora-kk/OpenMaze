"""Build an explicitly labeled draft PDF/HTML from the tracked Markdown paper."""
import argparse
import base64
import hashlib
import html
import json
import textwrap
from pathlib import Path

from markdown_it import MarkdownIt
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, XPreformatted
from benchmarks.provenance import provenance


def inline(tokens):
    result = []
    for token in tokens or []:
        if token.type == 'text':
            result.append(html.escape(token.content))
        elif token.type in ('softbreak', 'hardbreak'):
            result.append(' ' if token.type == 'softbreak' else '<br/>')
        elif token.type == 'code_inline':
            result.append('<font name="Courier">' + html.escape(token.content) + '</font>')
        elif token.type in ('strong_open', 'strong_close', 'em_open', 'em_close'):
            tag = 'b' if token.type.startswith('strong') else 'i'
            result.append('<' + ('/' if token.nesting < 0 else '') + tag + '>')
        elif token.type == 'link_open':
            href = token.attrGet('href') or ''
            result.append('<link href="' + html.escape(href, quote=True) + '" color="#174f79">')
        elif token.type == 'link_close':
            result.append('</link>')
        elif token.type == 'image':
            result.append(html.escape(token.content))
        else:
            result.append(html.escape(token.content))
    return ''.join(result)


def build(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    text = source.read_text()
    parser = MarkdownIt('commonmark', {'html': False}).enable('table')
    tokens = parser.parse(text)
    font_root = Path('/usr/share/fonts/truetype/dejavu')
    if (font_root / 'DejaVuSerif.ttf').is_file():
        font_files = {'PaperSerif': font_root / 'DejaVuSerif.ttf',
                      'PaperSerif-Bold': font_root / 'DejaVuSerif-Bold.ttf',
                      'PaperSerif-Italic': font_root / 'DejaVuSerif-Italic.ttf',
                      'PaperSerif-BoldItalic': font_root / 'DejaVuSerif-BoldItalic.ttf',
                      'PaperMono': font_root / 'DejaVuSansMono.ttf'}
    else:
        font_root = Path(reportlab.__file__).parent / 'fonts'
        font_files = {name: font_root / filename for name, filename in (
            ('PaperSerif', 'Vera.ttf'), ('PaperSerif-Bold', 'VeraBd.ttf'),
            ('PaperSerif-Italic', 'VeraIt.ttf'), ('PaperSerif-BoldItalic', 'VeraBI.ttf'),
            ('PaperMono', 'Vera.ttf'))}
    for name, font_path in font_files.items():
        pdfmetrics.registerFont(TTFont(name, str(font_path)))
    pdfmetrics.registerFontFamily('PaperSerif', normal='PaperSerif', bold='PaperSerif-Bold',
                                 italic='PaperSerif-Italic', boldItalic='PaperSerif-BoldItalic')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='PaperBody', fontName='PaperSerif', fontSize=10.5,
                              leading=14, spaceAfter=7))
    styles.add(ParagraphStyle(name='PaperCell', fontName='PaperSerif', fontSize=8,
                              leading=10, spaceAfter=3))
    styles.add(ParagraphStyle(name='PaperCode', fontName='PaperMono', fontSize=7,
                              leading=9, backColor=colors.HexColor('#f1f3f5'), spaceAfter=8))
    styles['Title'].fontName, styles['Title'].fontSize, styles['Title'].leading = 'PaperSerif-Bold', 19, 23
    for name in ('Heading1', 'Heading2', 'Heading3'):
        styles[name].fontName = 'PaperSerif-Bold'
        styles[name].keepWithNext = True
    story = [Paragraph('DEVELOPMENT DRAFT · NOT PEER REVIEWED', ParagraphStyle(
        'DraftNotice', parent=styles['PaperBody'], alignment=TA_CENTER, textColor=colors.HexColor('#8f391b'), fontSize=9))]
    images, heading, list_depth, in_table, rows, row = [], None, 0, False, [], []
    for token in tokens:
        if token.type == 'heading_open':
            heading = int(token.tag[1:])
        elif token.type == 'heading_close':
            heading = None
        elif token.type in ('bullet_list_open', 'ordered_list_open'):
            list_depth += 1
        elif token.type in ('bullet_list_close', 'ordered_list_close'):
            list_depth -= 1
        elif token.type == 'table_open':
            in_table, rows = True, []
        elif token.type == 'tr_open':
            row = []
        elif token.type == 'tr_close':
            rows.append(row)
        elif token.type == 'table_close':
            in_table = False
            width = (A4[0] - 1.5 * inch) / max(len(r) for r in rows)
            table = Table(rows, colWidths=[width] * max(len(r) for r in rows), repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9edf2')),
                ('LINEBELOW', (0, 0), (-1, 0), .6, colors.HexColor('#707a84')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
            ]))
            story += [table, Spacer(1, 10)]
        elif token.type == 'inline':
            if in_table:
                row.append(Paragraph(inline(token.children), styles['PaperCell']))
                continue
            child_images = [child for child in token.children or [] if child.type == 'image']
            if child_images:
                for child in child_images:
                    path = (source.parent / child.attrGet('src')).resolve()
                    if not path.is_file():
                        raise FileNotFoundError(f'missing local paper figure: {path}')
                    images.append(path)
                    figure = Image(str(path))
                    scale = min((A4[0] - 1.5 * inch) / figure.imageWidth, 3.8 * inch / figure.imageHeight)
                    figure.drawWidth, figure.drawHeight = figure.imageWidth * scale, figure.imageHeight * scale
                    story += [figure, Spacer(1, 8)]
                continue
            style = styles['Title'] if heading == 1 else styles[f'Heading{min(heading - 1, 3)}'] if heading else styles['PaperBody']
            body = inline(token.children)
            story.append(Paragraph(('• ' if list_depth and not heading else '') + body, style))
        elif token.type in ('fence', 'code_block'):
            code = '\n'.join(textwrap.fill(line, width=106, replace_whitespace=False, drop_whitespace=False)
                             for line in token.content.rstrip().splitlines())
            story.append(XPreformatted(html.escape(code), styles['PaperCode']))
        elif token.type == 'hr':
            story.append(Spacer(1, 10))

    pdf = output / 'openmaze-draft.pdf'
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont('PaperSerif', 7)
        canvas.setFillColor(colors.HexColor('#64707c'))
        canvas.drawString(.75 * inch, .4 * inch, 'OpenMaze · development draft · claims limited to reported evidence')
        canvas.drawRightString(A4[0] - .75 * inch, .4 * inch, str(document.page))
        canvas.restoreState()
    SimpleDocTemplate(str(pdf), pagesize=A4, rightMargin=.75 * inch, leftMargin=.75 * inch,
                      topMargin=.65 * inch, bottomMargin=.7 * inch,
                      title='OpenMaze research development draft', author='OpenMaze contributors').build(
                          story, onFirstPage=footer, onLaterPages=footer)
    rendered = parser.render(text)
    for path in images:
        relative = path.relative_to(source.parent).as_posix()
        mime = 'image/svg+xml' if path.suffix == '.svg' else 'image/png'
        data = 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
        rendered = rendered.replace('src="' + relative + '"', 'src="' + data + '"')
    html_path = output / 'openmaze-draft.html'
    html_path.write_text('<!doctype html><html><head><meta charset="utf-8"><title>OpenMaze draft</title>'
                         '<style>body{font:17px/1.55 Georgia,serif;max-width:850px;margin:48px auto;padding:0 24px}'
                         'table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #ccc;padding:8px}'
                         'pre{white-space:pre-wrap;background:#f1f3f5;padding:12px}img{max-width:100%}'
                         '.draft{color:#8f391b;font-family:sans-serif;font-size:13px}</style></head><body>'
                         '<p class="draft">DEVELOPMENT DRAFT · NOT PEER REVIEWED</p>' + rendered + '</body></html>')
    inputs = [source, *images]
    bibliography = source.parent / 'references.bib'
    if bibliography.exists():
        inputs.append(bibliography)
    manifest = {'scope': 'formatted development draft; PDF creation does not establish scientific validity',
                'provenance': provenance(),
                'inputs': {str(p.relative_to(source.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                'fonts': {name: {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for name, p in font_files.items()},
                'outputs': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (pdf, html_path)}}
    (output / 'paper-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('paper/main.md'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/paper'))
    args = parser.parse_args()
    print(build(args.source, args.output))


if __name__ == '__main__':
    main()
