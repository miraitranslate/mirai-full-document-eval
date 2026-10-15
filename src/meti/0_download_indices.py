
import hashlib
import json
import os
import re
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

REQUEST_INTERVAL_SEC: float = float(os.environ.get('METI_REQUEST_INTERVAL_SEC', '180'))
BLOCK_BACKOFF_SEC: float = float(os.environ.get('METI_BLOCK_BACKOFF_SEC', '900'))
MAX_CONSECUTIVE_FAILURES: int = 2
MAX_CONSECUTIVE_FORBIDDEN: int = 5
REFRESH_RECENT_INDEX_MONTHS: int = 2
EXIT_BLOCKED: int = 5
BLOCK_STATUSES: frozenset[int] = frozenset({202, 403, 405, 429, 500, 502, 503, 504})

RE_ARTICLE_HREF = re.compile(r'<a\s+[^>]*?href="\s*(/english/press/(\d{4})/[^"\s#?]+?\.html)\s*"')
RE_JA_LINK = re.compile(
    r'<a\s+[^>]*?href="\s*((?:https?://www\.meti\.go\.jp)?/press/[^"\s]+?\.html)\s*"[^>]*>\s*Japanese\s*</a>',
    re.IGNORECASE,
)


class Blocked(Exception):

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class StopRun(Exception):

    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code


def iter_yearmonths(oldest: int, newest: int) -> list[int]:
    """``oldest``〜``newest`` を YYYYMM の **有効な月だけ** 昇順で返す（12→翌1月へ繰上げ）。

    旧実装は ``range(oldest, newest+1)`` を生の整数で回し ``%100==13`` だけ補正していたため、
    月 14〜99（年あたり ~87 個）の存在しない yearmonth で無効 URL を叩いていた
    （不要なリクエスト）。本関数で有効月のみに限定する。
    """
    year, month = divmod(oldest, 100)
    result: list[int] = []
    while year * 100 + month <= newest:
        if 1 <= month <= 12:
            result.append(year * 100 + month)
        month += 1
        if month > 12:
            year += 1
            month = 1
    return result


class Pacer:

    def __init__(self, interval: float, max_requests: int = 0) -> None:
        self.interval = interval
        self.max_requests = max_requests
        self.count = 0
        self.consecutive_failures = 0
        self.consecutive_forbidden = 0
        self.stopped: Optional[StopRun] = None
        self.probe_url: Optional[str] = None
        self._last: Optional[float] = None

    def budget_left(self) -> bool:
        return self.max_requests <= 0 or self.count < self.max_requests

    def wait(self) -> None:
        if self._last is not None:
            elapsed = time.monotonic() - self._last
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
        self._last = time.monotonic()
        self.count += 1


def _is_blocked(response: Response) -> bool:
    status = getattr(response, 'status_code', 200)
    headers = getattr(response, 'headers', {}) or {}
    if status in BLOCK_STATUSES:
        return True
    if str(headers.get('x-amzn-waf-action', '')).strip():
        return True
    return 200 <= status < 300 and not (getattr(response, 'text', '') or '').strip()


def download_file(url: str, output_path: Path) -> None:
    """Download a file from a URL and save it to the given path."""
    tqdm.write(f"Downloading {url} > {output_path}")
    response: Response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=30)
    if _is_blocked(response):
        status = getattr(response, 'status_code', 0)
        raise Blocked(
            f"{url}: HTTP {status} "
            f"waf={(getattr(response, 'headers', {}) or {}).get('x-amzn-waf-action', '-')} "
            f"bytes={len(getattr(response, 'text', '') or '')}",
            status,
        )
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    tmp_path = output_path.with_name(output_path.name + '.part')
    tmp_path.write_text(response.text, encoding='utf-8')
    tmp_path.replace(output_path)


def _fetch(pacer: Pacer, url: str, output_path: Path) -> bool:
    if pacer.stopped is not None:
        raise pacer.stopped
    attempts = 0
    while True:
        if not pacer.budget_left():
            raise StopRun(0, f"--max-requests {pacer.max_requests} に到達")
        pacer.wait()
        attempts += 1
        counts_as_block = True
        try:
            download_file(url, output_path)
        except Blocked as blocked:
            if blocked.status != 403 and attempts == 1:
                if not pacer.budget_left():
                    raise StopRun(0, f"--max-requests {pacer.max_requests} に到達（再試行の予算なし）")
                tqdm.write(f"not fetched: {blocked}. {BLOCK_BACKOFF_SEC:.0f}s 待って 1 回だけ再試行する")
                time.sleep(BLOCK_BACKOFF_SEC)
                continue
            reason = f"blocked: {blocked}"
            if blocked.status == 403 and not pacer.budget_left():
                raise StopRun(0, f"--max-requests {pacer.max_requests} に到達（403 の確認の予算なし）")
            if blocked.status == 403 and _probe_says_ip_is_ok(pacer, url):
                reason = f"forbidden (article only; index {pacer.probe_url} is reachable): {url}"
                counts_as_block = False
                pacer.consecutive_failures = 0
                pacer.consecutive_forbidden += 1
                if pacer.consecutive_forbidden >= MAX_CONSECUTIVE_FORBIDDEN:
                    pacer.stopped = StopRun(
                        EXIT_BLOCKED,
                        f"記事の 403 が {MAX_CONSECUTIVE_FORBIDDEN} 件続いたため停止する"
                        "（index は取れるが記事が取れない。時間を置いて再実行する）",
                    )
                    raise pacer.stopped
        except requests.HTTPError as http_error:
            reason = f"http error: {http_error}"
            counts_as_block = False
        except requests.RequestException as net_error:
            reason = f"network error: {url}: {net_error}"
        else:
            pacer.consecutive_failures = 0
            pacer.consecutive_forbidden = 0
            return True

        if not counts_as_block:
            tqdm.write(f"skip (gone): {reason}")
            return False
        pacer.consecutive_failures += 1
        tqdm.write(f"skip ({pacer.consecutive_failures}/{MAX_CONSECUTIVE_FAILURES} consecutive): {reason}")
        if pacer.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            pacer.stopped = StopRun(
                EXIT_BLOCKED,
                f"{MAX_CONSECUTIVE_FAILURES} URL 連続で失敗したため停止する"
                "（取得済み分は残る。時間を置いて再実行すれば再開できる）",
            )
            raise pacer.stopped
        return False


def _probe_says_ip_is_ok(pacer: Pacer, url: str) -> bool:
    if not pacer.probe_url or pacer.probe_url == url or not pacer.budget_left():
        return False
    pacer.wait()
    try:
        response = requests.get(pacer.probe_url, headers={'User-Agent': USER_AGENT}, timeout=30)
    except requests.RequestException:
        return False
    return not _is_blocked(response) and getattr(response, 'status_code', 0) == 200


def _is_fetched(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _has_content(path: Path) -> bool:
    if _is_fetched(path):
        return True
    if path.exists():
        path.unlink()
    return False


def article_hrefs(index_html: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in RE_ARTICLE_HREF.finditer(index_html):
        href = match.group(1)
        if '/nBackIssue' in href or href.endswith('/index.html'):
            continue
        if href not in seen:
            seen.add(href)
            out.append(href)
    return out


def japanese_href(en_html: str) -> Optional[str]:
    match = RE_JA_LINK.search(en_html)
    return match.group(1).strip() if match else None


def known_en_uris(data_json: Optional[Path]) -> set[str]:
    if data_json is None or not data_json.exists():
        return set()
    return {r.get('en_URI', '') for r in json.loads(data_json.read_text(encoding='utf-8'))}


def _paths(base_uri: str, html_dir: Path, href: str) -> tuple[str, str, Path, Path]:
    en_uri = urljoin(base_uri, href)
    doc_id = f'meti_{hashlib.md5(en_uri.encode()).hexdigest()[:8]}'
    return doc_id, en_uri, html_dir / f'{doc_id}.en.html', html_dir / f'{doc_id}.ja.html'


def process_index(
    index_path: Path,
    base_uri: str,
    html_dir: Path,
    pacer: Pacer,
    out: Optional[list[str]] = None,
    cache_only: bool = False,
    skip_uris: Optional[set[str]] = None,
) -> list[str]:
    """Process an index file to extract metadata."""
    metadata: list[str] = out if out is not None else []
    skip_uris = skip_uris or set()
    index_html: str = index_path.read_text(encoding='utf-8')

    for href in article_hrefs(index_html):
        doc_id, en_uri, en_path, ja_path = _paths(base_uri, html_dir, href)
        if en_uri in skip_uris:
            continue

        if not _has_content(en_path):
            if cache_only or not _fetch(pacer, en_uri, en_path):
                continue

        ja_href = japanese_href(en_path.read_text(encoding='utf-8'))
        if not ja_href:
            tqdm.write(f"Japanese link not found: {en_uri}")
            continue
        ja_uri: str = urljoin(base_uri, ja_href)
        if not _has_content(ja_path):
            if cache_only or not _fetch(pacer, ja_uri, ja_path):
                continue

        metadata.append(f'{doc_id}\t{ja_path.name}\t{en_path.name}\t{ja_uri}\t{en_uri}')
    return metadata


def _pending_requests(index_path: Path, html_dir: Path, base_uri: str, skip_uris: set[str]) -> int:
    pending = 0
    for href in article_hrefs(index_path.read_text(encoding='utf-8')):
        _, en_uri, en_path, ja_path = _paths(base_uri, html_dir, href)
        if en_uri in skip_uris:
            continue
        if not _is_fetched(en_path):
            pending += 2
        elif not _is_fetched(ja_path):
            pending += 1
    return pending


@click.command()
@click.argument('oldest_yearmonth', type=int)
@click.argument('newest_yearmonth', type=int)
@click.argument('output_tsv', type=click.Path(writable=True, path_type=Path))
@click.option('--html_directory', default='html', type=click.Path(file_okay=False, path_type=Path), help="Directory to save HTML files")
@click.option('--base_uri', default='https://www.meti.go.jp/', help="Base URI for downloading files")
@click.option('--index_uri', default='https://www.meti.go.jp/english/press/nBackIssue', help="Base index URI")
@click.option('--index_directory', default='indices', type=click.Path(file_okay=False, path_type=Path), help="Directory to save index files")
@click.option('--interval', '--delay', 'interval', default=REQUEST_INTERVAL_SEC, type=float, help="Seconds between consecutive requests (default 180)")
@click.option('--max-requests', default=0, type=int, help="Stop after this many requests in this run (0 = unlimited). Progress is kept.")
@click.option('--skip-in', 'skip_in', default=None, type=click.Path(dir_okay=False, path_type=Path), help="既存 data.json。ここに en_URI がある記事は取得も TSV 出力もしない")
def main(
    oldest_yearmonth: int,
    newest_yearmonth: int,
    output_tsv: Path,
    html_directory: Path,
    base_uri: str,
    index_uri: str,
    index_directory: Path,
    interval: float,
    max_requests: int,
    skip_in: Optional[Path],
) -> None:
    html_directory.mkdir(parents=True, exist_ok=True)
    index_directory.mkdir(parents=True, exist_ok=True)
    pacer = Pacer(interval, max_requests)
    skip_uris = known_en_uris(skip_in)
    if skip_uris:
        tqdm.write(f"skip-in: data.json 既存の {len(skip_uris)} URI は取得しない")

    yearmonths = sorted(iter_yearmonths(oldest_yearmonth, newest_yearmonth), reverse=True)
    recent = set(yearmonths[:REFRESH_RECENT_INDEX_MONTHS])

    metadata = ["doc_id\tja_file\ten_file\tja_URI\ten_URI"]
    stop: Optional[StopRun] = None
    for yearmonth in tqdm(yearmonths, desc="months"):
        index_path = index_directory / f"{yearmonth}.html"
        cache_only = stop is not None
        try:
            month_index_uri = f"{index_uri}{yearmonth}.html"
            if not cache_only and (yearmonth in recent or not _has_content(index_path)):
                if _fetch(pacer, month_index_uri, index_path):
                    pacer.probe_url = month_index_uri
            if not _is_fetched(index_path):
                continue
            if not cache_only:
                pending = _pending_requests(index_path, html_directory, base_uri, skip_uris)
                tqdm.write(f"{yearmonth}: 未取得 {pending} リクエスト × {interval:.0f}s ≈ {pending * interval / 60:.0f} 分")
            process_index(
                index_path, base_uri, html_directory, pacer, out=metadata, cache_only=cache_only, skip_uris=skip_uris
            )
        except StopRun as s:
            tqdm.write(f"stop: {s} — 残りの月はキャッシュ分のみで TSV を作る（exit {s.code}）")
            stop = s
            if _is_fetched(index_path):
                process_index(
                    index_path, base_uri, html_directory, pacer, out=metadata, cache_only=True, skip_uris=skip_uris
                )

    seen_ids: set[str] = set()
    rows: list[str] = []
    for row in metadata:
        doc_id = row.split('\t', 1)[0]
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        rows.append(row)
    output_tsv.write_text("\n".join(rows), encoding="utf-8")
    tqdm.write(f"TSV written to {output_tsv} ({len(rows) - 1} pairs, {pacer.count} requests this run)")
    if stop is not None and stop.code:
        raise click.exceptions.Exit(code=stop.code)


if __name__ == '__main__':
    main()
