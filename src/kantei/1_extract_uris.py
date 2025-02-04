import re
from re import Pattern, Match
import click
from pathlib import Path
from tqdm import tqdm
from typing import Optional


@click.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
def extract_uris(directory: Path):
    """
    Extracts URIs from HTML files in the given DIRECTORY and prints them as full URLs.
    """
    uri_pattern: Pattern[str] = re.compile(r'href="(/(\d+(_[a-z]+?)?/actions/\d{6}/.+?\.html))"')
    uris: set[str] = set()

    for html_file in tqdm(directory.glob("*.html")):
        with html_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                match: Optional[Match[str]] = uri_pattern.search(line)
                if match:
                    uris.add(match.group(1))

    for uri in sorted(uris):
        tqdm.write(f"https://japan.kantei.go.jp{uri}")


if __name__ == "__main__":
    extract_uris()
