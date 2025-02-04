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
DEFAULT_DELAY: float = 1.0


def download_file(url: str, destination: Path, delay: float) -> None:
    """指定URLからコンテンツを取得し、ファイルへ保存する。"""
    response: Response = requests.get(url)
    response.encoding = response.apparent_encoding
    # 再ダウンロードを避けるため、取得結果をファイルへ書き出す
    with open(destination, 'w', encoding='utf-8') as f:
        f.write(response.text)
    tqdm.write(f'Saved to {destination}')
    time.sleep(delay)


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
def main(oldest_yearmonth: int, output_tsv: Path, html_directory: Path, base_uri: str, index_uri: str, index_file: Path, delay: float) -> None:
    """
    指定された年月（oldest_yearmonth 以上）より新しい文書のリンクをスクレイピングし、
    TSV 形式で出力する。
    """
    # HTML を保存するディレクトリがなければ作成
    html_directory.mkdir(parents=True, exist_ok=True)

    # インデックスファイルが存在しなければダウンロード
    if not index_file.exists():
        download_file(index_uri, index_file, delay)

    total_lines: int = count_lines(index_file)
    tsv_entries: list[str] = []
    with open(index_file, 'r', encoding='utf-8') as f:
        for line in tqdm(f, total=total_lines):
            match: Optional[Match[str]] = re.search(r'<a href="(.+?)"', line)

            if match:
                en_uri: str = urllib.parse.urljoin(base_uri, match.group(1))
                doc_id: str = DOC_ID_PREFIX + hashlib.md5(en_uri.encode()).hexdigest()[:8]
                yearmonth_match: Optional[Match[str]] = re.search(r'(20\d{6})(-\d+)?\.html', en_uri)

                if yearmonth_match:
                    yearmonth: int = int(yearmonth_match.group(1)[:6])
                    if yearmonth >= oldest_yearmonth:
                        tqdm.write(f'English Link Extracted: {en_uri}')
                        base_filename: str = Path(en_uri).stem
                        en_file: Path = html_directory / f'{base_filename}.en'
                        ja_file: Path = html_directory / f'{base_filename}.ja'
                        if not en_file.exists():
                            download_file(en_uri, en_file, delay)

                        with open(en_file, encoding='utf-8') as f:
                            for line in f:
                                ja_match: Optional[Match[str]] = re.search(r'<a target="_blank" href="(.+?)">Japanese(<img.+?)?</a>', line) # relative uri
                                if ja_match:
                                    ja_uri: str = urllib.parse.urljoin(base_uri, ja_match.group(1))
                                    tqdm.write(f'Japanese Link Extracted: {ja_uri}')
                                    if not ja_file.exists():
                                        download_file(ja_uri, ja_file, delay)
                                        tsv_entries.append(f"{doc_id}\t{ja_file.name}\t{en_file.name}\t{ja_uri}\t{en_uri}")
                                    break

    with output_tsv.open('w', encoding='utf-8') as f:
        f.write('doc_id\tja_filename\ten_filename\tja_uri\ten_uri\n')
        f.write('\n'.join(tsv_entries))


if __name__ == '__main__':
    main()
