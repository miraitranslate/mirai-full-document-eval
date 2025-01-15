import argparse
import json
import os
import sys

from bs4 import BeautifulSoup


def extract_date(html):
    # extract date from <meta name="date">
    date_text=''
    for meta in html.find_all('meta'):
        if 'name' in meta.attrs and meta.attrs['name']=='date':
            date_text=meta.attrs['content']
            break
    return date_text

def extract_main_text(html):
    paragraphs=[]
    main=html.find('section', class_='content-section')
    if not main:
        main=html.find('div', class_='unique-block')
    for p in main.find_all(['p', 'h2', 'ol', 'ul']):
        if p.name=='h2':
            text=p.get_text('', strip=True).strip()
        elif p.name in ['ol', 'ul']:
            for li in p.find_all('li'):
                text=li.get_text('', strip=True).strip()
                if text:
                    paragraphs.append(text)
            continue
        else:
            if p.find('li'):
                continue
            text=p.get_text('', strip=True).strip()
        if text:
            paragraphs.append(text)
    if not paragraphs:
        # get text in main
        text=main.get_text('', strip=True).strip()
        if text:
            text=text.split('\n\n')
            paragraphs.extend(text)
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
            existing[en_URI]=1
            id=id.replace('mf_', 'mof_') # 歴史的経緯
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

