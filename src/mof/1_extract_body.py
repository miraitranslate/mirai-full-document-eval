import json
from pathlib import Path
import click
from bs4 import BeautifulSoup, Tag, NavigableString
from typing import Optional


HTML_TAG = NavigableString | Tag

def extract_date(html: BeautifulSoup) -> str:
    """Extract the publication date from <meta name="date">."""
    for meta in html.find_all('meta', attrs={'name': 'date'}):
        return meta.get('content', '').strip()
    return ''


def extract_main_text(html: BeautifulSoup) -> list[str]:
    """Extract main text content from specific sections in the HTML."""
    paragraphs: list[str] = []
    main: Optional[HTML_TAG] = html.find('section', class_='content-section') or html.find('div', class_='unique-block')
    if not main:
        return paragraphs

    for element in main.find_all(['p', 'h2', 'ol', 'ul']):
        text: str = ''
        if element.name == 'h2':
            text = element.get_text('', strip=True).strip()
        elif element.name in ['ol', 'ul']:
            for li in element.find_all('li'):
                text = li.get_text('', strip=True).strip()
                if text:
                    paragraphs.append(text)
            continue
        else:
            if element.find('li'):
                continue
            text = element.get_text('', strip=True).strip()
        if text:
            paragraphs.append(text)

    if not paragraphs:
        # get text in main
        text: str = main.get_text('', strip=True).strip()
        if text:
            paragraphs.extend(text.split('\n\n'))

    return paragraphs


def is_num_newlines(paragraphs0: list[str], paragraphs1: list[str]) -> bool:
    """Check if the number of newlines matches between two lists of paragraphs."""
    return all(p0.count('\n') == p1.count('\n') for p0, p1 in zip(paragraphs0, paragraphs1))


@click.command()
@click.argument('input_tsv', type=click.Path(exists=True, path_type=Path))
@click.argument('output_json', type=click.Path(writable=True, path_type=Path))
@click.option('--html_directory', default='html', type=click.Path(file_okay=False, path_type=Path), help="Directory containing HTML files.")
def main(input_tsv: Path, output_json: Path, html_directory: Path) -> None:
    """Process the input TSV and extract data into a JSON output."""
    metadata: list[dict[str, str]] = []
    existing: set[str] = set()

    with input_tsv.open() as f:
        next(f)  # Skip the header
        for line in f:
            id: str
            ja_file: str
            en_file: str
            ja_uri: str
            en_uri: str
            id, ja_file, en_file, ja_uri, en_uri = line.strip().split('\t')
            if en_uri in existing:
                continue
            existing.add(en_uri)
            id = id.replace('mf_', 'mof_')  # 歴史的経緯
            metadata.append({
                'id': id,
                'ja_file': ja_file,
                'en_file': en_file,
                'ja_URI': ja_uri,
                'en_URI': en_uri
            })

    data: list[dict[str, str | list[str]]] = []
    for item in metadata:
        click.echo(f"Processing ID: {item['id']}", err=True)

        en_path: Path = html_directory / item['en_file']
        ja_path: Path = html_directory / item['ja_file']

        en_html: str = en_path.read_text(encoding='utf-8')
        ja_html: str = ja_path.read_text(encoding='utf-8')

        en_soup: BeautifulSoup = BeautifulSoup(en_html, 'html.parser')
        ja_soup: BeautifulSoup = BeautifulSoup(ja_html, 'html.parser')

        en_text: list[str] = extract_main_text(en_soup)
        ja_text: list[str] = extract_main_text(ja_soup)

        if not en_text or not ja_text:
            click.echo(f"None: {item['id']}", err=True)
            continue

        if len(en_text) != len(ja_text):
            click.echo(f"不一致: {item['id']}", err=True)
            continue

        if not is_num_newlines(en_text, ja_text):
            click.echo(f"改行数不一致: {item['id']}", err=True)
            continue

        ja_date: str = extract_date(ja_soup)

        data.append({
            'id': item['id'],
            'en_URI': item['en_URI'],
            'ja_URI': item['ja_URI'],
            'en_body': en_text,
            'ja_body': ja_text,
            'ja_date': ja_date
        })

    with output_json.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent='\t')
    # print the number of data
    click.echo(f"Processed {len(data)} items.", err=True)


if __name__ == '__main__':
    main()