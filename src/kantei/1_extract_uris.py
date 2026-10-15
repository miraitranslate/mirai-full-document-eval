import re
from re import Pattern
import click
from pathlib import Path
from tqdm import tqdm

URI_PATTERN: Pattern[str] = re.compile(r'href="(/(\d+(_[a-z]+?)?/actions/\d{6}/(?!index\.html)[^"/]+?\.html))"')
OG_URL_PATTERN: Pattern[str] = re.compile(r'property="og:url"\s+content="([^"]+)"|content="([^"]+)"\s+property="og:url"')
BASE_URI: str = "https://japan.kantei.go.jp"
MONTH_PATTERN: Pattern[str] = re.compile(r'/actions/(\d{6})/')


def downloaded_uris(html_directory: Path) -> set[str]:
    found: set[str] = set()
    for html_file in html_directory.glob("*"):
        if not html_file.is_file():
            continue
        try:
            text = html_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = OG_URL_PATTERN.search(text)
        if match:
            found.add(match.group(1) or match.group(2))
    return found


@click.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--exclude-downloaded",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="このディレクトリに og:url が一致する HTML が既にある URI を出力しない（毎月の全件再取得を避ける）",
)
@click.option("--oldest", type=int, default=None, help="URL の月（/actions/YYYYMM/）がこれより前の記事を出力しない")
def extract_uris(directory: Path, exclude_downloaded: Path | None, oldest: int | None):
    """
    Extracts article URIs from index HTML files in DIRECTORY and prints them as full URLs.
    """
    uris: set[str] = set()
    for html_file in tqdm(directory.glob("*.html")):
        for match in URI_PATTERN.finditer(html_file.read_text(encoding="utf-8")):
            uris.add(match.group(1))

    skip: set[str] = set()
    if exclude_downloaded is not None and exclude_downloaded.is_dir():
        skip = downloaded_uris(exclude_downloaded)

    for uri in sorted(uris):
        full = f"{BASE_URI}{uri}"
        if full in skip:
            continue
        month = MONTH_PATTERN.search(uri)
        if oldest is not None and month and int(month.group(1)) < oldest:
            continue
        tqdm.write(full)


if __name__ == "__main__":
    extract_uris()
