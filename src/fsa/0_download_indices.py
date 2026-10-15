import datetime
import hashlib
import re
import time
import urllib.parse
from pathlib import Path
import click
import requests
from requests import Response
from typing import Optional
from re import Match
from tqdm import tqdm

DOC_ID_PREFIX: str = 'fsa_'
DEFAULT_HTML_DIR: str = 'html'
DEFAULT_BASE_URI: str = 'https://www.fsa.go.jp/'
DEFAULT_INDEX_URI: str = 'https://www.fsa.go.jp/en/news/index.html'
DEFAULT_INDEX_FILE: str = 'index.html'
ARCHIVE_URI_TEMPLATE: str = 'https://www.fsa.go.jp/en/news/{year}.html'
DEFAULT_DELAY: float = 1.0


def download_file(url: str, destination: Path, delay: float) -> None:
    """指定URLからコンテンツを取得し、ファイルへ保存する。"""
    response: Response = requests.get(url, timeout=30)
    if response.status_code != 200:
        tqdm.write(f'HTTP {response.status_code}: {url}（保存しない）')
        time.sleep(delay)
        return
    response.encoding = response.apparent_encoding
    # 再ダウンロードを避けるため、取得結果をファイルへ書き出す
    with open(destination, 'w', encoding='utf-8') as f:
        f.write(response.text)
    tqdm.write(f'Saved to {destination}')
    time.sleep(delay)


def index_pages(oldest_yearmonth: int, index_uri: str, index_file: Path, today: datetime.date) -> list[tuple[str, Path, bool]]:
    pages: list[tuple[str, Path, bool]] = [(index_uri, index_file, True)]
    for year in range(oldest_yearmonth // 100, today.year):
        archive_file = index_file.with_name(f'archive_{year}.html')
        pages.append((ARCHIVE_URI_TEMPLATE.format(year=year), archive_file, year >= today.year - 1))
    return pages


def count_lines(filename: Path, encoding: str ='utf-8') -> int:
    with open(filename, 'r', encoding=encoding) as f:
        return sum(1 for _ in f)


@click.command()
@click.argument('oldest_yearmonth', type=int)
@click.argument('output_tsv', type=click.Path(writable=True, path_type=Path))
@click.option('--html_directory', default=DEFAULT_HTML_DIR, type=click.Path(file_okay=False, path_type=Path))
@click.option('--base_uri', default=DEFAULT_BASE_URI, type=str)
@click.option('--index_uri', default=DEFAULT_INDEX_URI, type=str)
@click.option('--index_file', default=DEFAULT_INDEX_FILE, type=click.Path(path_type=Path))
@click.option('--delay', default=DEFAULT_DELAY, type=float)
@click.option('--newest', 'newest_yearmonth', default=None, type=int, help="この年月より後の文書は出力しない")
def main(oldest_yearmonth: int, output_tsv: Path, html_directory: Path, base_uri: str, index_uri: str, index_file: Path, delay: float, newest_yearmonth: Optional[int]) -> None:
    """
    指定された年月（oldest_yearmonth 以上）より新しい文書のリンクをスクレイピングし、
    TSV 形式で出力する。
    """
    # HTML を保存するディレクトリがなければ作成
    html_directory.mkdir(parents=True, exist_ok=True)

    tsv_entries: list[str] = []
    seen_uris: set[str] = set()
    for page_uri, page_file, refresh in index_pages(oldest_yearmonth, index_uri, index_file, datetime.date.today()):
        if refresh or not page_file.exists():
            download_file(page_uri, page_file, delay)
        if not page_file.exists():
            continue
        tsv_entries.extend(_scan_index(page_file, oldest_yearmonth, html_directory, base_uri, delay, seen_uris, newest_yearmonth))

    with output_tsv.open('w', encoding='utf-8') as f:
        f.write('doc_id\tja_filename\ten_filename\tja_uri\ten_uri\n')
        f.write('\n'.join(tsv_entries))


def _scan_index(
    index_file: Path, oldest_yearmonth: int, html_directory: Path, base_uri: str, delay: float, seen_uris: set[str],
    newest_yearmonth: Optional[int] = None,
) -> list[str]:
    total_lines: int = count_lines(index_file)
    tsv_entries: list[str] = []
    with open(index_file, 'r', encoding='utf-8') as f:
        for line in tqdm(f, total=total_lines):
            match: Optional[Match[str]] = re.search(r'<a href="(.+?)"', line)

            if match:
                en_uri: str = urllib.parse.urljoin(base_uri, match.group(1))
                doc_id: str = DOC_ID_PREFIX + hashlib.md5(en_uri.encode()).hexdigest()[:8]
                yearmonth_match: Optional[Match[str]] = re.search(r'(20\d{6})(-\d+)?\.html', en_uri)

                if yearmonth_match and en_uri not in seen_uris:
                    seen_uris.add(en_uri)
                    yearmonth: int = int(yearmonth_match.group(1)[:6])
                    if yearmonth >= oldest_yearmonth and (newest_yearmonth is None or yearmonth <= newest_yearmonth):
                        tqdm.write(f'English Link Extracted: {en_uri}')
                        base_filename: str = doc_id
                        en_file: Path = html_directory / f'{base_filename}.en'
                        ja_file: Path = html_directory / f'{base_filename}.ja'
                        if not en_file.exists():
                            download_file(en_uri, en_file, delay)
                        if not en_file.exists():
                            continue

                        with open(en_file, encoding='utf-8') as f:
                            for line in f:
                                ja_match: Optional[Match[str]] = re.search(r'<a target="_blank" href="(.+?)">Japanese(<img.+?)?</a>', line) # relative uri
                                if ja_match:
                                    ja_uri: str = urllib.parse.urljoin(base_uri, ja_match.group(1))
                                    tqdm.write(f'Japanese Link Extracted: {ja_uri}')
                                    if not ja_file.exists():
                                        download_file(ja_uri, ja_file, delay)
                                    if ja_file.exists():
                                        tsv_entries.append(f"{doc_id}\t{ja_file.name}\t{en_file.name}\t{ja_uri}\t{en_uri}")
                                    break
    return tsv_entries


if __name__ == '__main__':
    main()
