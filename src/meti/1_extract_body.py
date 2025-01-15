
import argparse
import json
import os
import re
import sys

from bs4 import BeautifulSoup, Comment


def extract_date(html):
    # extract date from <div class="main">
    date_text=''
    main=html.find('div', class_='main')
    if main:
        # extract date from <p class="b-g">
        date=main.find('p', class_='b-g')
        if date:
            date=re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date.text)
            if date:
                year, month, day=date.groups()
                date_text=year+'-'+month.zfill(2)+'-'+day.zfill(2)
    return date_text

def extract_main_text(html):
    paragraphs=[]
    # <div class="main">
    main=html.find('div', class_='main')
    # iterate each element, and if it is <p> or <div class="border_box">, extract text
    if main:
        text_stack=[]
        for e in main.children:
            text=''
            if e.name=='p':
                text=e.get_text('', strip=True)
            elif e.name=='div' and e.get('class')==['border_box']:
                text=e.get_text('', strip=True)
            elif e.name=='ul' or e.name=='ol':
                for li in e.find_all('li'):
                    text+=li.get_text('', strip=True)+'\n'
            elif e.name=='h2':
                text=e.get_text('', strip=True)
                if text.lower() in ['関連資料', '関連リンク', '担当', 'division in charge', 'related materials', 'reference links', 'related link'] or 'related link' in text.lower():
                    break
            elif e.name=='figure':
                text=e.get_text('', strip=True)
            elif isinstance(e, str) and not isinstance(e, Comment):
                text=e.strip()
                text=re.sub(r'\n\s+', '\n', text)
                text=re.sub(r'[ 　\t]{2,}', ' ', text)
                if text:
                    text_stack.append(text)
                continue
            elif e.name=='a':
                text=e.get_text('', strip=True)
                if text:
                    text_stack.append(text)
                continue
            text=re.sub(r'\n\n+', '\n', text)
            text=text.strip()
            if text:
                if text_stack:
                    paragraphs.append(''.join(text_stack))
                    text_stack=[]
                paragraphs.append(text)
        if text_stack:
            paragraphs.append(''.join(text_stack))
    return paragraphs

def check_num_newlines(paragraphs0, paragraphs1):
    # Count the number of lines in each paragraph.
    # If in one paragraph the number of lines is different from the other, return False.
    for p0, p1 in zip(paragraphs0, paragraphs1):
        if p0.count('\n') != p1.count('\n'):
            return False
    return True

def main(args):
    tsv_path=args.input_tsv
    html_dir=args.html_directory
    output_json=args.output_json
    metadata=[]
    existing={}
    with open(tsv_path) as f:
        next(f)
        for l in f:
            id, ja_file, en_file, ja_URI, en_URI=l.strip().split('\t')
            if en_URI in existing:
                continue
            if en_URI==ja_URI:
                continue
            existing[en_URI]=1
            id=id.replace('_news', '')
            metadata.append({
                'id': id,
                'ja_file': ja_file,
                'en_file': en_file,
                'ja_URI': ja_URI,
                'en_URI': en_URI
            })
    data=[]
    for m in metadata:
        print(m['id'], file=sys.stderr)
        with open(os.path.join(html_dir, m['en_file'])) as f:
            en_html=f.read()
        with open(os.path.join(html_dir, m['ja_file'])) as f:
            ja_html=f.read()
        en_soup=BeautifulSoup(en_html, 'html.parser')
        ja_soup=BeautifulSoup(ja_html, 'html.parser')
        en_text=extract_main_text(en_soup)
        ja_text=extract_main_text(ja_soup)
        if not en_text or not ja_text:
            print('None: ', m['id'], file=sys.stderr)
            continue
        if len(en_text)!=len(ja_text):
            print('不一致: ', m['id'], len(en_text), len(ja_text), file=sys.stderr)
            continue
        if not check_num_newlines(en_text, ja_text):
            print('改行数不一致: ', m['id'], file=sys.stderr)
            continue
        ja_date=extract_date(ja_soup)
        data.append({
            'id': m['id'],
            'en_URI': m['en_URI'],
            'ja_URI': m['ja_URI'],
            'en_body':  en_text,
            'ja_body': ja_text,
            'ja_date': ja_date,
        })
    with open(output_json, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent="\t")
    # print the number of data
    print(len(data), file=sys.stderr)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input_tsv')
    parser.add_argument('output_json')
    parser.add_argument('--html_directory', default='html')
    args = parser.parse_args()
    main(args)

