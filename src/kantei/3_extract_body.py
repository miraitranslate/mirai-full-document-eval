import datetime
import hashlib
import json
import re
from re import Match, Pattern
from typing import Optional
import time
from pathlib import Path
import click
import requests
from tqdm import tqdm
from bs4 import BeautifulSoup, Tag, NavigableString
from urllib.parse import urljoin

BASE_JA_URI: str = 'https://www.kantei.go.jp/'
BASE_EN_URI: str = 'https://japan.kantei.go.jp/'
RE_URI: Pattern[str] = re.compile(r'//(?:www\.)?kantei\.go\.jp/jp/')
RE_BARE_JA_HOST: Pattern[str] = re.compile(r'^https?://kantei\.go\.jp/')
HTML_TAG = Tag | NavigableString


def remove_empty_paragraphs(paragraphs: list[str]) -> list[str]:
    return [para.strip() for para in paragraphs if para.strip() != '']


def is_num_newlines(paragraphs0: list[str], paragraphs1: list[str]) -> bool:
    return all(p0.count('\n') == p1.count('\n') for p0, p1 in zip(paragraphs0, paragraphs1))


NEW_CONTAINER_CLASSES: tuple[str, ...] = ('section', 'article-content')
PARAGRAPH_BLOCK_CLASSES: tuple[str, ...] = ('m_text', 'en_t')
RE_PROVISIONAL: Pattern[str] = re.compile(r'^\[?\s*provisional\s+translation\s*\]?\.?$', re.IGNORECASE)


def _find_container_new(soup: BeautifulSoup) -> Optional[Tag]:
    for cls in NEW_CONTAINER_CLASSES:
        div = soup.find('div', class_=cls)
        if isinstance(div, Tag):
            return div
    return None


def _strip_boilerplate(div: Tag) -> None:
    for e in div.find_all('div', class_='aly_tx_right'):
        e.decompose()
    for e in div.find_all(class_='p_right'):
        e.decompose()
    for e in div.find_all('p', align='right'):
        e.decompose()
    for e in div.find_all('p', style=re.compile(r'text-align\s*:\s*right')):
        e.decompose()
    for e in div.find_all(['button', 'style', 'script']):
        e.decompose()


def _paragraph_blocks(div: Tag) -> list[Tag]:
    blocks: list[Tag] = []
    for el in div.find_all(['p', 'div']):
        if el.name == 'div' and not set(el.get('class') or []) & set(PARAGRAPH_BLOCK_CLASSES):
            continue
        if el.find_parent('p') is not None:
            continue
        if el.find_parent('div', class_=list(PARAGRAPH_BLOCK_CLASSES)) is not None:
            continue
        blocks.append(el)
    return blocks


def is_only_provisional_marker(paragraphs: Optional[list[str]]) -> bool:
    return bool(paragraphs) and all(RE_PROVISIONAL.match(p.strip()) for p in paragraphs)


def get_body_en(soup: BeautifulSoup, version: str) -> Optional[list[str]]:
    if version not in ['new', 'old']:
        raise ValueError(f'Invalid version: {version}. Must be "new" or "old".')

    div = _find_container_new(soup) if version == 'new' else soup.find('div', id='format')
    if not isinstance(div, Tag):
        return None

    _strip_boilerplate(div)

    if version == 'new':
        blocks = _paragraph_blocks(div)
        if blocks:
            paragraphs: list[str] = []
            for block in blocks:
                paragraphs.extend(_split_paragraphs(block.get_text()))
            return paragraphs

    paragraphs = _split_paragraphs(div.get_text())
    if version == 'new' and len(paragraphs) > 1 and RE_PROVISIONAL.match(paragraphs[0]):
        paragraphs = paragraphs[1:]
    return paragraphs


def _split_paragraphs(raw: str) -> list[str]:
    # nbsp (U+00A0) を半角スペースへ。デコード済み文字列では 1 文字 '\xa0'。
    # 旧実装の '\xc2\xa0' は UTF-8 バイト列のリテラル（2 文字）で正常文字列に一致せず no-op だった。
    text: str = raw.strip().replace('\xa0', ' ')
    text = re.sub(r'\n\s+\n', '\n\n', text)
    return remove_empty_paragraphs(text.split('\n\n'))


def get_self_uri(soup: BeautifulSoup) -> Optional[str]:
    meta_tag = soup.find('meta', property='og:url')
    return meta_tag.get('content') if meta_tag else None


def get_japanese_uri(soup: BeautifulSoup) -> Optional[str]:
    link = soup.find('a', href=RE_URI)
    if link:
        uri = link['href']
        if not uri.startswith('http'):
            uri = urljoin(BASE_JA_URI, uri)
        return RE_BARE_JA_HOST.sub(BASE_JA_URI, uri)
    return None


def get_body_ja(soup: BeautifulSoup) -> Optional[list[str]]:
    div = _find_container_new(soup)
    if div is None:
        return None
    _strip_boilerplate(div)

    for br in div.find_all('br'):
        following = br.next_sibling
        if not (isinstance(following, NavigableString) and str(following).startswith('\n')):
            br.replace_with('\n')

    paragraphs: list[str] = []
    for block in _paragraph_blocks(div):
        text: str = block.get_text().strip().replace('\t', '')
        paragraphs.extend(remove_empty_paragraphs(text.split('\n　')))
    return paragraphs


def get_date_ja(soup: BeautifulSoup) -> Optional[str]:
    span: Optional[HTML_TAG] = soup.find('span', class_='date')
    if not span:
        span = soup.select_one('.article-date time') or soup.find(class_='article-date')
    if not span:
        return None

    dt = convert_str_date_into_datetime(span.get_text())
    if dt:
        return dt.isoformat()
    return None


def convert_str_date_into_datetime(str_date: str) -> Optional[datetime.date]:
    match: Optional[Match[str]] = re.search(r'(平成|令和)(\d{1,2}|元)年(\d{1,2})月(\d{1,2})日', str_date)
    if match:
        era, year, month, day = match.groups()
        if era == '平成':
            base_year = 1988
        else:
            base_year = 2018

        if year == '元':
            year_num = base_year + 1
        else:
            year_num = base_year + int(year)

        return datetime.date(year_num, int(month), int(day))
    return None


def get_version(soup: BeautifulSoup) -> str:
    return 'new' if soup.find('div', id='top') else 'old'


def download_and_save_html(url: str, output_path: Path) -> None:
    response = requests.get(
        url,
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 12.0; Win32; x86) '
                'AppleWebKit/934.78 (KHTML, like Gecko) '
                'Chrome/315.0.0.0 Safari/779.68 Edge/43.29855'
            )
        },
        timeout=30,
    )
    response.encoding = response.apparent_encoding
    output_path.write_text(response.text, encoding='utf-8')


def generate_uid(uri: str) -> str:
    return hashlib.md5(uri.encode()).hexdigest()[:8]


@click.command()
@click.argument('en_directory', type=click.Path(exists=True, path_type=Path))
@click.argument('ja_directory', type=click.Path(file_okay=False, path_type=Path))
@click.argument('output_json', type=click.Path(writable=True, path_type=Path))
@click.option('--uris', 'uris_file', type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None, help="この一覧（1 行 1 URI）にある記事だけを抽出する")
def main(en_directory: Path, ja_directory: Path, output_json: Path, uris_file: Optional[Path]) -> None:
    all_data: list[dict[str, Optional[str] | Optional[list[str]]]] = []
    ids: set[str] = set()

    wanted: Optional[set[str]] = None
    if uris_file is not None:
        wanted = {line.strip() for line in uris_file.read_text(encoding='utf-8').splitlines() if line.strip()}

    file_list = list(en_directory.glob('*'))
    total_files = len(file_list)

    for i, en_path in enumerate(tqdm(file_list, total=total_files, desc='Processing files', dynamic_ncols=True), start=1):
        soup: BeautifulSoup = BeautifulSoup(en_path.read_text(encoding='utf-8'), 'html.parser')
        version: str = get_version(soup)
        en_uri: Optional[str] = get_self_uri(soup)
        if wanted is not None and en_uri not in wanted:
            continue
        en_body: Optional[list[str]] = get_body_en(soup, version)
        if is_only_provisional_marker(en_body):
            tqdm.write(f'[{i}/{total_files}] en_body が [Provisional translation] のみ: {en_path}')
            en_body = None
        ja_uri: Optional[str] = get_japanese_uri(soup)

        # 途中で情報が足りない場合はスキップ
        if not all([en_uri, ja_uri, en_body]):
            tqdm.write(f'[{i}/{total_files}] en_URI, ja_URI, en_bodyのいずれかがNone: {en_path}')
            continue

        # id は en_URI から生成する（ファイル名だけだと別文書で衝突しうるため）。
        uid = f'kantei_{generate_uid(en_uri)}'
        if uid in ids:
            # 同一 en_URI の重複は当該文書だけスキップする（他の異常系と同じ）。
            # 全停止 (sys.exit) すると重複 1 件で kantei 抽出が丸ごと落ち、
            # 無人月次が止まるため。集約側でも id 主キーで重複排除される。
            tqdm.write(f'[{i}/{total_files}] 重複IDをスキップ: {uid}')
            continue
        ids.add(uid)

        ja_basename: str = en_uri.replace(BASE_EN_URI, '').replace('/', '--').replace('.html', '')
        ja_path: Path = ja_directory / f'{ja_basename}.html'

        if not ja_path.exists():
            tqdm.write(f'[{i}/{total_files}] ダウンロードする: {ja_path}')
            download_and_save_html(ja_uri, ja_path)
            time.sleep(1)

        ja_soup: BeautifulSoup = BeautifulSoup(ja_path.read_text(encoding='utf-8'), 'html.parser')
        ja_body: Optional[list[str]] = get_body_ja(ja_soup)
        ja_date: Optional[str] = get_date_ja(ja_soup)

        # 元のコード同様、日付が取れない場合もスキップ
        if ja_body is None or ja_date is None:
            tqdm.write(f'[{i}/{total_files}] Error: ja_bodyまたはja_dateがNone: {ja_path}')
            continue

        # 段落数が一致しなかったらスキップ
        if len(en_body) != len(ja_body):
            tqdm.write(f'[{i}/{total_files}] 段落数不一致: {en_path} と {ja_path}')
            continue

        # 改行数が一致しなかったらスキップ
        if not is_num_newlines(en_body, ja_body):
            tqdm.write(f'[{i}/{total_files}] 改行数不一致: {en_path}')
            continue

        # 問題なければデータに追加
        all_data.append({
            'id': uid,
            'en_URI': en_uri,
            'ja_URI': ja_uri,
            'en_body': en_body,
            'ja_body': ja_body,
            'ja_date': ja_date
        })

    with output_json.open('w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent="\t")

    tqdm.write(f'処理済みデータ数: {len(all_data)}')


if __name__ == '__main__':
    main()
