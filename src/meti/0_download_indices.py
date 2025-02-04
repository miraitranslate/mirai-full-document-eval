import hashlib
import re
from re import Match
import time
from pathlib import Path
from typing import Optional
import click
import requests
from tqdm import tqdm
from urllib.parse import urljoin
from requests import Response

BASE_UR: str = 'https://www.meti.go.jp/'
USER_AGENT: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'


def download_file(url: str, output_path: Path, delay: float) -> None:
    """Download a file from a URL and save it to the given path."""
    try:
        tqdm.write(f"Downloading {url} > {output_path}")
        response: Response = requests.get(url, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        output_path.write_text(response.text, encoding='utf-8')
        time.sleep(delay)
    except requests.RequestException as e:
        tqdm.write(f"Error downloading {url}: {e}")


def process_index(index_path: Path, base_uri: str, html_dir: Path, delay: float) -> list[str]:
    """Process an index file to extract metadata."""
    metadata: list[str] = []
    index_html: str = index_path.read_text(encoding='utf-8')

    match: Optional[Match[str]]
    for match in tqdm(re.finditer(r'<a href="(/english/press/.+?)"', index_html)):
        en_uri: str = urljoin(base_uri, match.group(1))
        doc_id: str = f'meti_{hashlib.md5(en_uri.encode()).hexdigest()[:8]}'

        # skip if filename does not contain digits
        if not re.search(r'\d', en_uri):
            continue

        # download en_html
        en_file: str = f'{doc_id}.en.html'
        en_path: Path = html_dir / en_file
        tqdm.write(f"Processing {en_uri} > {en_path}")
        if not en_path.exists():
            download_file(en_uri, en_path, delay)

            # find a link to ja_html in en_html such as <a href="/press/2024/06/20240620002/20240620002.html">Japanese</a>
            en_html: str = en_path.read_text(encoding='utf-8')
            ja_match: Optional[Match[str]] = re.search(r'<a href="(/press/.*?\.html)">Japanese</a>', en_html)

            if ja_match:
                ja_uri: str = urljoin(base_uri, ja_match.group(1))
                ja_file: str = f'{doc_id}.ja.html'
                ja_path: Path = html_dir / ja_file

                if not ja_path.exists():
                    download_file(ja_uri, ja_path, delay)

                metadata.append(f'{doc_id}\t{ja_file}\t{en_file}\t{ja_uri}\t{en_uri}')
    return metadata


@click.command()
@click.argument('oldest_yearmonth', type=int)
@click.argument('newest_yearmonth', type=int)
@click.argument('output_tsv', type=click.Path(writable=True, path_type=Path))
@click.option('--html_directory', default='html', type=click.Path(file_okay=False, path_type=Path), help="Directory to save HTML files")
@click.option('--base_uri', default='https://www.meti.go.jp/', help="Base URI for downloading files")
@click.option('--index_uri', default='https://www.meti.go.jp/english/press/nBackIssue', help="Base index URI")
@click.option('--index_directory', default='indices', type=click.Path(file_okay=False, path_type=Path), help="Directory to save index files")
@click.option('--delay', default=1.0, type=float, help="Delay between requests in seconds")
def main(
    oldest_yearmonth: int,
    newest_yearmonth: int,
    output_tsv: Path,
    html_directory: Path,
    base_uri: str,
    index_uri: str,
    index_directory: Path,
    delay: float,
) -> None:
    html_directory.mkdir(parents=True, exist_ok=True)
    index_directory.mkdir(parents=True, exist_ok=True)

    metadata = ["doc_id\tja_file\ten_file\tja_URI\ten_URI"]

    # Download index files
    for yearmonth in tqdm(range(oldest_yearmonth, newest_yearmonth + 1), desc="Downloading index files"):
        if yearmonth % 100 == 13:
            yearmonth += 88
        index_uri_full: str = f"{index_uri}{yearmonth}.html"
        index_path: Path = index_directory / f"{yearmonth}.html"

        if not index_path.exists():
            download_file(index_uri_full, index_path, delay)

    # extract en_uri from indices
    for index_path in tqdm(index_directory.glob("*.html"), desc="Processing index files"):
        metadata.extend(process_index(index_path, base_uri, html_directory, delay))
        time.sleep(delay)
    # Write output TSV
    output_tsv.write_text("\n".join(metadata), encoding="utf-8")
    tqdm.write(f"TSV written to {output_tsv}")


if __name__ == '__main__':
    main()
