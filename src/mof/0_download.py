import datetime
import hashlib
import re
from re import Match
import time
from pathlib import Path
from urllib.parse import urljoin
import click
import requests
from typing import Optional
from requests import Response
from tqdm import tqdm


def add_a_month(date: datetime.datetime) -> datetime.datetime:
    """Add one month to the given datetime object."""
    year: int = date.year
    month: int = date.month
    if month == 12:
        year += 1
        month = 1
    else:
        month += 1
    return datetime.datetime(year, month, 1)


@click.command()
@click.argument('from_yearmonth', type=str)
@click.argument('to_yearmonth', type=str)
@click.argument('output_tsv', type=click.Path(writable=True, path_type=Path))
@click.argument('html_dir', type=click.Path(file_okay=False, path_type=Path))
def main(from_yearmonth: str, to_yearmonth: str, output_tsv: Path, html_dir: Path) -> None:
    """Download MOF HTML files and generate a TSV file linking English and Japanese versions."""

    from_date: datetime.datetime = datetime.datetime.strptime(from_yearmonth, '%Y%m')
    to_date: datetime.datetime = datetime.datetime.strptime(to_yearmonth, '%Y%m')

    html_dir.mkdir(parents=True, exist_ok=True)

    index_uri_template: str = 'https://www.mof.go.jp/english/public_relations/whats_new/{yearmonth}.html'

    # Generate a list of year-month strings
    yearmonths: list[str] = []
    current: datetime.datetime = from_date
    while current <= to_date:
        yearmonths.append(current.strftime('%Y%m'))
        current = add_a_month(current)

    # Download index files
    for yearmonth in tqdm(yearmonths, desc='Downloading index files', total=len(yearmonths)):
        index_uri: str = index_uri_template.format(yearmonth=yearmonth)
        response: Response = requests.get(index_uri)
        response.encoding = response.apparent_encoding
        index_path: Path = html_dir / f'index_{yearmonth}.html'
        index_path.write_text(response.text, encoding='utf-8')

    # Prepare TSV data
    tsv: list[str] = ['id\tja_file\ten_file\tja_URI\ten_URI']

    for yearmonth in tqdm(yearmonths, desc='Processing index files', total=len(yearmonths)):
        index_path: Path = html_dir / f'index_{yearmonth}.html'
        html: str = index_path.read_text(encoding='utf-8')
        index_uri: str = index_uri_template.format(yearmonth=yearmonth)

        for line in html.split('\n'):
            if '<li class="information-item">' in line:
                if any(keyword in line for keyword in [
                    'JGBs', 'PRI', 'Trade Statistics', 'FILP', 'Exchequer', 'Currency',
                    'Balance of', 'International Reserves/Foreign Currency Liquidity'
                ]):
                    continue

                match: Optional[Match[str]] = re.search(r'<a href="(.+?)"', line)
                if not match:
                    continue

                en_uri: str = urljoin(index_uri, match.group(1))
                if not en_uri.endswith(('.htm', '.html')):
                    continue

                doc_id: str = hashlib.md5(en_uri.encode()).hexdigest()[:8]
                tqdm.write(f"Processing English URI: {en_uri}")

                en_file: Path = html_dir / f'mof_{doc_id}.en.html'
                en_response: Response = requests.get(en_uri)
                en_response.encoding = en_response.apparent_encoding
                en_file.write_text(en_response.text, encoding='utf-8')

                for subline in en_response.text.split('\n'):
                    ja_match: Optional[Match[str]] = re.search(
                        r'<div class="text-right"><a href="(.+?)" class="button -arrow-r -sm">Japanese</a></div>',
                        subline
                    )
                    if ja_match:
                        ja_uri: str = urljoin(en_uri, ja_match.group(1))
                        tqdm.write(f"Processing Japanese URI: {ja_uri}")

                        ja_file: Path = html_dir / f'mof_{doc_id}.ja.html'
                        ja_response: Response = requests.get(ja_uri)
                        ja_response.encoding = ja_response.apparent_encoding
                        ja_file.write_text(ja_response.text, encoding='utf-8')

                        tsv.append(f"{doc_id}\t{ja_file.name}\t{en_file.name}\t{ja_uri}\t{en_uri}")
                        time.sleep(1)
                        break

    # Write the output TSV file
    output_tsv.write_text('\n'.join(tsv), encoding='utf-8')
    tqdm.write(f"TSV file written to {output_tsv}")


if __name__ == '__main__':
    main()
