import json
import re
from re import Match
from pathlib import Path
from typing import Optional
import click
from bs4 import BeautifulSoup, Comment, Tag, NavigableString
from tqdm import tqdm

HTML_TAG = Tag | NavigableString


def extract_date(html: BeautifulSoup) -> str:
    # extract date from <div class="main">
    date_text: str = ''
    main: Optional[HTML_TAG] = html.find('div', class_='main')
    if main:
        # extract date from <p class="b-g">
        date: Optional[HTML_TAG] = main.find('p', class_='b-g')
        if date:
            match: Match[str] = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date.text)
            if match:
                year, month, day = match.groups()
                date_text: str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return date_text


def extract_main_text(html: BeautifulSoup) -> list[str]:
    """Extract the main text content from the HTML."""
    paragraphs: list[str] = []
    # <div class="main">

    main: Optional[HTML_TAG] = html.find('div', class_='main')
    if not main:
        return paragraphs

    # iterate each element, and if it is <p> or <div class="border_box">, extract text
    text_stack: list[str] = []
    element: HTML_TAG
    for element in main.children:
        text: str = ''
        if element.name == 'p':
            text = element.get_text('', strip=True)
        elif element.name == 'div' and element.get('class') == ['border_box']:
            text = element.get_text('', strip=True)
        elif element.name in ['ul', 'ol']:
            for li in element.find_all('li'):
                text += li.get_text('', strip=True) + '\n'

        elif element.name == 'h2':
            text = element.get_text('', strip=True)
            if text.lower() in ['関連資料', '関連リンク', '担当', 'division in charge', 'related materials', 'reference links', 'related link'] or 'related link' in text.lower():
                break
        elif element.name == 'figure':
            text = element.get_text('', strip=True)

        elif isinstance(element, str) and not isinstance(element, Comment):
            text = element.strip()
            text = re.sub(r'\n\s+', '\n', text)
            text = re.sub(r'[ \u3000\t]{2,}', ' ', text)
            if text:
                text_stack.append(text)
            continue

        elif element.name == 'a':
            text = element.get_text('', strip=True)
            if text:
                text_stack.append(text)
            continue

        text = re.sub(r'\n\n+', '\n', text).strip()
        if text:
            if text_stack:
                paragraphs.append(''.join(text_stack))
                text_stack = []
            paragraphs.append(text)

    if text_stack:
        paragraphs.append(''.join(text_stack))
    return paragraphs


def is_num_newlines(paragraphs0: list[str], paragraphs1: list[str]) -> bool:
    """Check if the number of newlines matches between two lists of paragraphs."""
    return all(p0.count('\n') == p1.count('\n') for p0, p1 in zip(paragraphs0, paragraphs1))


@click.command()
@click.argument('input_tsv', type=click.Path(exists=True, path_type=Path))
@click.argument('output_json', type=click.Path(writable=True, path_type=Path))
@click.option('--html_directory', default='html', type=click.Path(file_okay=False, path_type=Path), help="Directory containing HTML files.")
def main(input_tsv: Path, output_json: Path, html_directory: Path) -> None:
    """Main function to process the input TSV and generate a JSON output."""
    metadata: list[dict[str, str]] = []
    existing: set[str]= set()

    with input_tsv.open() as f:
        next(f)  # Skip the header
        for line in f:
            id, ja_file, en_file, ja_uri, en_uri = line.strip().split('\t')
            if en_uri in existing or en_uri == ja_uri:
                continue

            existing.add(en_uri)
            metadata.append({
                'id': id.replace('_news', ''),
                'ja_file': ja_file,
                'en_file': en_file,
                'ja_URI': ja_uri,
                'en_URI': en_uri
            })

    data: list[dict[str, str | list[str]]] = []
    for item in tqdm(metadata):
        tqdm.write(f"Processing ID: {item['id']}")

        en_path: Path = html_directory / item['en_file']
        ja_path: Path = html_directory / item['ja_file']

        en_html: str = en_path.read_text(encoding='utf-8')
        ja_html: str = ja_path.read_text(encoding='utf-8')

        en_soup: BeautifulSoup = BeautifulSoup(en_html, 'html.parser')
        ja_soup: BeautifulSoup = BeautifulSoup(ja_html, 'html.parser')

        en_text: list[str] = extract_main_text(en_soup)
        ja_text: list[str] = extract_main_text(ja_soup)

        if not en_text or not ja_text:
            tqdm.write(f"None: {item['id']}")
            continue

        if len(en_text) != len(ja_text):
            tqdm.write(f"不一致: {item['id']}")
            continue

        if not is_num_newlines(en_text, ja_text):
            tqdm.write(f"改行数不一致: {item['id']}")
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
    tqdm.write(f"Processed {len(data)} items.")


if __name__ == '__main__':
    main()
