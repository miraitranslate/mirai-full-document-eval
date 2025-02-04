
import datetime
import json
import re
from re import Match, Pattern
import unicodedata
from pathlib import Path
from typing import Optional
import click
from bs4 import BeautifulSoup, Tag
from tqdm import tqdm

# 正規表現パターン（例："平成22年6月30日", "令和元年5月1日", "2010年6月30日"）
JAPANESE_DATE_REGEX: Pattern[str] = re.compile(
    r'(?:(平成|令和)(\d{1,2}|元)|(\d{4}))(?:年|月)(\d+)月(\d+)日'
)


def parse_japanese_date(match: Optional[Match[str]]) -> str:
    """正規表現のマッチ結果から日付文字列（YYYY-MM-DD）を生成する．

    Args:
        match: 日付にマッチした正規表現のMatchオブジェクト

    Returns:
        マッチした場合はYYYY-MM-DD形式の日付文字列、マッチしなかった場合は空文字
    """
    if not match:
        return ""
    year: int = 0
    month: int
    day: int

    if match.group(1) in ("平成", "令和"):
        era: str = match.group(1)
        era_year: str = match.group(2)
        if era == "平成":
            base_year: int = 1988
        else:  # "令和"
            base_year = 2018
        if era_year != "元":
            year = base_year + int(era_year)
        else:
            year = base_year
    else:
        year = int(match.group(3))
    month = int(match.group(4))
    day = int(match.group(5))
    try:
        dt: datetime.date = datetime.date(year, month, day)
    except ValueError:
        return ""
    return dt.strftime("%Y-%m-%d")


def is_style_right_aligned(element: Tag) -> bool:
    """style属性が 'text-align:right' であるか判定する．
    空白や末尾のセミコロンを除去して判定する．
    """
    style: str = element.get("style", "")
    normalized_style: str = style.replace(" ", "").rstrip(";")
    return normalized_style == "text-align:right"


def is_right_aligned(element: Tag) -> bool:
    """要素が右寄せと判定できるかどうかを返す．
    具体的には style 属性が 'text-align: right' 系であるか，
    またはクラスに 'a-right' が含まれているかどうかで判定する．
    """
    if is_style_right_aligned(element):
        return True
    classes: Optional[list[str] | str] = element.get("class")
    if isinstance(classes, list) and "a-right" in classes:
        return True
    return False


def extract_date_from_html(soup: BeautifulSoup) -> str:
    """HTMLから日付文字列（YYYY-MM-DD）を抽出する．
    まず<p class="mb0 mt0">内を探し，
    次に右寄せまたは'a-right'クラスのある<p>や<div>を探索し，
    最後に'a-center'クラスのある要素から探す．
    """
    # 優先: <p class="mb0 mt0">
    date_element: Optional[Tag] = soup.find("p", class_="mb0 mt0")
    if date_element:
        text: str = unicodedata.normalize("NFKC", date_element.get_text('', strip=True).strip())
        date_str: str = parse_japanese_date(JAPANESE_DATE_REGEX.search(text))
        if date_str:
            return date_str

    # 右寄せ、または 'a-right' クラスの要素から探索
    for element in soup.find_all(["p", "div"]):
        if is_right_aligned(element):
            text = unicodedata.normalize("NFKC", element.get_text('', strip=True).strip())
            date_str = parse_japanese_date(JAPANESE_DATE_REGEX.search(text))
            if date_str:
                return date_str

    # 'a-center' クラスの要素から探索
    for element in soup.find_all(["p", "div"]):
        classes: Optional[list[str]] = element.get("class")
        if classes and "a-center" in classes:
            text = unicodedata.normalize("NFKC", element.get_text('', strip=True).strip())
            date_str = parse_japanese_date(JAPANESE_DATE_REGEX.search(text))
            if date_str:
                return date_str

    return ""


def add_trailing_space(text: str) -> str:
    """文字列の末尾が英字の場合、末尾に半角スペースを追加して返す．"""
    if text and text[-1].isalpha():
        return text + " "
    return text


def extract_list_text(list_element: Tag) -> str:
    """リスト要素(<ul>または<ol>)から各<li>のテキストを再帰的に取得する．"""
    result: str = ""
    for li in list_element.find_all("li", recursive=False):
        # リスト内にさらにリストがあれば再帰する
        if li.find(["ul", "ol"]):
            result += extract_list_text(li) + "\n"
        else:
            result += li.get_text('', strip=True).strip() + "\n"
    return result.strip()


def extract_text_elements(container: Tag) -> list[str]:
    """
    container 内の各要素ごとにテキストを抽出する．
    見出し、段落、リスト、定義リスト、表などを処理する．
    """
    paragraphs: list[str] = []
    for element in container.children:
        if not isinstance(element, Tag):
            continue

        text: str = ""
        tag_name: str = element.name.lower() if element.name else ""

        if tag_name == "div":
            paragraphs.extend(extract_text_elements(element))

        elif tag_name == "p":
            # <br> を含む場合はplain text抽出に任せる
            if element.find("br"):
                paragraphs.extend(extract_plain_text(element))
                continue
            text = element.get_text('', strip=True).strip()

        elif tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            text = element.get_text('', strip=True).strip()

        elif tag_name in ["ul", "ol"]:
            text = extract_list_text(element).strip()

        elif tag_name == "dl":
            dt_text: str = "\n".join(dt.get_text('', strip=True).strip() for dt in element.find_all("dt"))
            dd_text: str = "\n".join(dd.get_text('', strip=True).strip() for dd in element.find_all("dd"))
            text = (dt_text + "\n" + dd_text).strip()

        elif tag_name == "table":
            # テーブルは各セルをスペースで、行を改行で結合するが，
            # 問い合わせ先等の場合は無視する
            table_text: str = ""
            for tr in element.find_all("tr"):
                row_text = " ".join(
                    td.get_text('', strip=True).strip() for td in tr.find_all(["td", "th"])
                )
                table_text += row_text + "\n"
            if "問い合わせ先" in table_text or "Contact" in table_text:
                continue
            text = table_text.strip()
            text = re.sub(r'\s+\n', '\n', text)
            text = ''
        # else:
        #     text = element.get_text('', strip=True).strip()

        text = re.sub(r'\([Pp]rovisional translation.*?\)', '', text)
        text = re.sub(r'  +', ' ', text)
        text = re.sub(r'\n +', '\n', text)
        text = re.sub(r'\n\n+', '\n', text)
        text = text.strip()

        if text:
            paragraphs.append(text)
    return paragraphs


def extract_plain_text(container: Tag) -> list[str]:
    """
    container の子要素からプレーンテキストを抽出する．
    改行やタグ毎に段落を区切る処理を行う．
    """
    paragraphs: list[str] = []
    current_paragraph: list[str] = []

    for child in container.children:
        if isinstance(child, str):
            current_paragraph.append(add_trailing_space(child.strip()))

        elif isinstance(child, Tag):
            tag_name: str = child.name.lower() if child.name else ""
            if tag_name == "h1":
                if current_paragraph:
                    paragraphs.append("".join(current_paragraph).strip())
                    current_paragraph = []
                paragraphs.append(child.get_text(strip=True))

            elif tag_name == "br":
                if current_paragraph:
                    paragraphs.append("".join(current_paragraph).strip())
                    current_paragraph = []

            elif tag_name in ["a", "span", "strong"]:
                current_paragraph.append(add_trailing_space(child.get_text(strip=True)))

            elif tag_name == "div":
                # div 内部は再帰的に処理
                inner_paragraphs: list[str] = extract_plain_text(child)
                if current_paragraph:
                    paragraphs.append("".join(current_paragraph).strip())
                    current_paragraph = []
                paragraphs.extend(inner_paragraphs)
            else:
                current_paragraph.append(add_trailing_space(child.get_text(strip=True)))

    if current_paragraph:
        paragraphs.append("".join(current_paragraph).strip())

    # 空文字列は除去
    return [para for para in paragraphs if para]


def extract_main_text_from_html(soup: BeautifulSoup) -> list[str]:
    """
    HTML内の <div id="main"> 以下の本文テキストを抽出する．
    不要な要素（シェアボタンや連絡先、右寄せなど）は除去する．
    """
    paragraphs: list[str] = []
    main_div: Optional[Tag] = soup.find("div", id="main")
    if not main_div:
        return paragraphs

    inner_div: Optional[Tag] = main_div.find("div", class_="inner")
    if not inner_div:
        return paragraphs

    content_div: Tag = inner_div

    # 不要な要素の除去
    for unwanted in content_div.find_all("p", class_="share-button"):
        unwanted.decompose()
    for unwanted in content_div.find_all("dl", class_="contact_box"):
        unwanted.decompose()

    # 右寄せ・notice・caution クラスを持つ要素を除去
    to_decompose: list[Tag] = []
    for element in content_div.find_all(["p", "div"]):
        classes: Optional[list[str]] = element.get("class")
        if is_style_right_aligned(element):
            to_decompose.append(element)
        elif classes and ("a-right" in classes):
            to_decompose.append(element)
        elif classes and "notice" in classes:
            to_decompose.append(element)
        elif classes and "caution" in classes:
            to_decompose.append(element)
    for element in to_decompose:
        element.decompose()

    # 段落数を判定し，<p>タグがなければ plain text 抽出
    content_text: str = content_div.get_text()
    content_text = re.sub(r'\n', '', content_text)
    content_text = re.sub(r'\s+', ' ', content_text)

    p_tags: list[Tag] = content_div.find_all("p")
    if not p_tags:
        paragraphs = extract_plain_text(content_div)
    else:
        paragraphs = extract_text_elements(content_div)

    return paragraphs


def check_newline_counts(paragraphs_a: list[str], paragraphs_b: list[str]) -> bool:
    """
    2つの段落リストにおいて，各段落内の改行数が一致するかチェックする．
    """
    for para_a, para_b in zip(paragraphs_a, paragraphs_b):
        if para_a.count("\n") != para_b.count("\n"):
            return False
    return True


def contains_not_found(paragraphs: list[str]) -> bool:
    """
    段落内に '404 Not Found' が含まれているか判定する．
    """
    return any("404 Not Found" in para for para in paragraphs)


def read_metadata(tsv_path: Path) -> list[dict[str, str]]:
    """
    入力TSVファイルから重複のないメタデータリストを作成する．

    TSVの各行は id, ja_file, en_file, ja_URI, en_URI のタブ区切りを前提とする．
    """
    metadata: list[dict[str, str]] = []
    seen_en_uri: dict[str, bool] = {}

    with tsv_path.open(encoding="utf-8") as f:
        # ヘッダーをスキップ
        next(f)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 5:
                continue
            record_id, ja_file, en_file, ja_uri, en_uri = parts[:5]
            if en_uri in seen_en_uri:
                continue
            seen_en_uri[en_uri] = True
            metadata.append({
                "id": record_id,
                "ja_file": ja_file,
                "en_file": en_file,
                "ja_URI": ja_uri,
                "en_URI": en_uri,
            })
    return metadata


@click.command()
@click.argument("input_tsv", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("output_json", type=click.Path(dir_okay=False, writable=True, path_type=Path))
@click.option("--html_directory", "-d", type=click.Path(file_okay=False, path_type=Path), default=Path("html"), help="HTMLファイルが格納されたディレクトリ")
def main(input_tsv: Path, output_json: Path, html_directory: Path) -> None:
    """
    入力TSVとHTMLファイルから記事の本文と日付情報を抽出し、JSONファイルに出力する．
    """
    metadata_list: list[dict[str, str]] = read_metadata(input_tsv)
    extracted_data: list[dict[str, str | list[str]]] = []

    for record in tqdm(metadata_list, desc="Processing records", unit="record"):
        tqdm.write(f"Processing ID: {record['id']}")

        en_file_path: Path = html_directory / record["en_file"]
        ja_file_path: Path = html_directory / record["ja_file"]


        en_html: str = en_file_path.read_text(encoding="utf-8")
        ja_html: str = ja_file_path.read_text(encoding="utf-8")

        en_soup: BeautifulSoup = BeautifulSoup(en_html, "html.parser")
        ja_soup: BeautifulSoup = BeautifulSoup(ja_html, "html.parser")

        en_paragraphs: list[str] = extract_main_text_from_html(en_soup)
        ja_paragraphs: list[str] = extract_main_text_from_html(ja_soup)

        # エラー判定
        if contains_not_found(en_paragraphs) or contains_not_found(ja_paragraphs):
            tqdm.write(f"Not Found: {record['id']}")
            continue
        if not en_paragraphs or not ja_paragraphs:
            tqdm.write(f"本文取得失敗: {record['id']}")
            continue
        if len(en_paragraphs) != len(ja_paragraphs):
            tqdm.write(f"段落数不一致: {record['id']} (EN: {len(en_paragraphs)}, JA: {len(ja_paragraphs)})")
            continue
        if not check_newline_counts(en_paragraphs, ja_paragraphs):
            tqdm.write(f"改行数不一致: {record['id']}")
            continue

        ja_date: str = extract_date_from_html(BeautifulSoup(ja_html, "html.parser"))
        if not ja_date:
            tqdm.write(f"日付抽出失敗: {record['id']}")
            continue

        extracted_data.append({
            "id": record["id"],
            "en_URI": record["en_URI"],
            "ja_URI": record["ja_URI"],
            "en_body": en_paragraphs,
            "ja_body": ja_paragraphs,
            "ja_date": ja_date,
        })

    try:
        output_json.write_text(json.dumps(extracted_data, ensure_ascii=False, indent="\t"), encoding="utf-8")
    except Exception as e:
        tqdm.write(f"JSON書き込みエラー: {e}")
        return

    tqdm.write(f"抽出件数: {len(extracted_data)}")


if __name__ == "__main__":
    main()
