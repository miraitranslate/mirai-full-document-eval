import argparse
import datetime
import json
import os
import re
import sys
import unicodedata

from bs4 import BeautifulSoup, Tag

DATE=re.compile(r'(?:(平成|令和)(\d{1,2}|元)|(\d{4}))(?:年|月)(\d+)月(\d+)日') # /news/21/ginkou/20100630-5.html が平成22月6月30日になっている

def re_date(m):
    if m:
        year=0
        month=0
        day=0
        if m.group(1)=='平成':
            year=1988+int(m.group(2)) if m.group(2)!='元' else 1988
        elif m.group(1)=='令和':
            year=2018+int(m.group(2)) if m.group(2)!='元' else 2018
        else:
            year=int(m.group(3))
        month=int(m.group(4))
        day=int(m.group(5))
        d=datetime.date(year, month, day)
        date_text=d.strftime('%Y-%m-%d')
        return date_text
    return ''

def extract_date(html):
    date_text=''
    # extract japanese date from <p class="mb0 mt0">...</p>
    date=html.find('p', class_='mb0 mt0')
    if date:
        date_text=date.get_text().strip()
        date_text=unicodedata.normalize('NFKC', date_text)
        m=DATE.search(date_text)
        date_text=re_date(m)
    else:
        # iterate p and div
        for e in html.find_all(['p', 'div']):
            # if style text-align:right or class is a-right
            if 'text-align: right' in e.get('style', '') or e.get('style')=='text-align:right' or e.get('style')=='text-align: right' or e.get('style')=='text-align: right;' or e.get('style')=='text-align:right;' or (e.get('class') and 'a-right' in e.get('class')):
                date_text=e.get_text('', strip=True).strip()
                date_text=unicodedata.normalize('NFKC', date_text)
                m=DATE.search(date_text)
                date_text=re_date(m)
                if date_text:
                    break
    if not date_text:
        for e in html.find_all(['p', 'div']):
            if 'a-center' in e.get('class', ''):
                date_text=e.get_text('', strip=True).strip()
                date_text=unicodedata.normalize('NFKC', date_text)
                m=DATE.search(date_text)
                date_text=re_date(m)
                if date_text:
                    break
    return date_text

def extract_main_text(html):
    paragraphs=[]
    # extract <div id="main">
    main=html.find('div', id='main')
    if not main:
        return paragraphs
    # extract <div class="inner">
    inner=main.find('div', class_='inner')
    if not inner:
        return paragraphs
    main=inner
    # remove <p class="share-button">
    for e in main.find_all('p', class_='share-button'):
        e.decompose()
    # remove <dl class="contact_box">
    for e in main.find_all('dl', class_='contact_box'):
        e.decompose()
    to_decompose=[]
    for e in main.find_all(['p', 'div']):
        if e.get('style')=='text-align:right' or e.get('style')=='text-align: right' or e.get('style')=='text-align: right;' or e.get('style')=='text-align:right;':
            to_decompose.append(e)
        elif e.get('class') and 'a-right' in e.get('class'):
            to_decompose.append(e)
        elif e.get('class') and 'notice' in e.get('class'):
            to_decompose.append(e)
        elif e.get('class') and 'caution' in e.get('class'):
            to_decompose.append(e)
    for e in to_decompose:
        e.decompose()
    # count the number of <p>
    p_count=len(main.find_all('p'))
    # get main text
    main_text=main.get_text()
    main_text=re.sub(r'\n', '', main_text)
    main_text=re.sub(r'\s+', ' ', main_text)
    
    # <br>で段落が作られている場合
    if p_count==0:
        paragraphs=extract_plain_text(main)
    else:
        paragraphs=extract_elements(main)
    return paragraphs

def spacer(text):
    if len(text)>0 and text[-1].isalpha():
        return text+' '
    return text

def get_list_items(ulol):
    list_text=''
    for li in ulol.find_all('li'):
        if li.find('ul') or li.find('ol'):
            list_text+=get_list_items(li)
        else:
            list_text+=li.get_text('', strip=True).strip()+'\n'
    return list_text.strip()

def extract_elements(main):
    paragraphs=[]
    for e in main.children:
        text=''
        if e.name=='div':
            paragraphs.extend(extract_elements(e))
        if e.name=='p':
            if e.find('br'):
                p=extract_plain_text(e)
                if p:
                    paragraphs.extend(p)
                continue
            text=e.get_text('', strip=True).strip()
            text=re.sub(r'\s+\n', '\n', text)
        elif e.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            text=e.get_text('', strip=True).strip()
        elif e.name=='ul' or e.name=='ol':
            list_text=get_list_items(e)
            text=list_text.strip()
        elif e.name=='dl':
            list_text=''
            for dt in e.find_all('dt'):
                list_text+=dt.get_text('', strip=True).strip()+'\n'
            for dd in e.find_all('dd'):
                list_text+=dd.get_text('', strip=True).strip()+'\n'
            text=list_text.strip()
        elif e.name=='table':
            # cells are separated with space, rows are separated with newline, and whole the table is packed into one paragraph
            table_text=''
            for tr in e.find_all('tr'):
                for td in tr.find_all(['td', 'th']):
                    table_text+=td.get_text('', strip=True).strip()+' '
                table_text+='\n'
            if '問い合わせ先' in table_text or 'Contact' in table_text:
                continue
            text=table_text.strip()
            text=re.sub(r'\s+\n', '\n', text)
            text='' # この際、tableは無視する
        text=re.sub(r'\([Pp]rovisional translation.*?\)', '', text)
        text=re.sub(r'  +', ' ', text)
        text=re.sub(r'\n +', '\n', text)
        text=re.sub(r'\n\n+', '\n', text)
        text=text.strip()
        if text:
            paragraphs.append(text)
    return paragraphs

def extract_plain_text(element):
    paragraphs=[]
    current_paragraph=[]
    for tag in element.children:
        if isinstance(tag, str):
            current_paragraph.append(spacer(tag.strip()))
        elif isinstance(tag, Tag):
            if tag.name == 'h1':
                if current_paragraph:
                    paragraphs.append(''.join(current_paragraph).strip())
                    current_paragraph = []
                paragraphs.append(tag.get_text(strip=True))
            elif tag.name == 'br':
                if current_paragraph:
                    paragraphs.append(''.join(current_paragraph).strip())
                    current_paragraph = []
            elif tag.name in ['a', 'span', 'strong']:
                current_paragraph.append(spacer(tag.get_text(strip=True)))
            elif tag.name == 'div':
                internal_paragraphs = extract_plain_text(tag)
                if current_paragraph:
                    paragraphs.append(''.join(current_paragraph).strip())
                    current_paragraph = []
                paragraphs.extend(internal_paragraphs)
            else:
                current_paragraph.append(spacer(tag.get_text(strip=True)))

    if current_paragraph:
        paragraphs.append(''.join(current_paragraph).strip())

    return [para for para in paragraphs if para]
        
def check_num_newlines(paragraphs0, paragraphs1):
    # Count the number of lines in each paragraph.
    # If in one paragraph the number of lines is different from the other, return False.
    for p0, p1 in zip(paragraphs0, paragraphs1):
        if p0.count('\n') != p1.count('\n'):
            return False
    return True

def is_not_found(paragraphs):
    for para in paragraphs:
        if '404 Not Found' in para:
            return True
    return False

def main(args):
    input_tsv=args.input_tsv
    output_json=args.output_json
    html_directory=args.html_directory
    metadata=[]
    existing={}
    with open(input_tsv) as f:
        next(f)
        for l in f:
            id, ja_file, en_file, ja_URI, en_URI=l.strip().split('\t')
            if en_URI in existing:
                continue
            existing[en_URI]=1
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
        with open(os.path.join(html_directory, m['en_file'])) as f:
            en_html=f.read()
        with open(os.path.join(html_directory, m['ja_file'])) as f:
            ja_html=f.read()
        en_soup=BeautifulSoup(en_html, 'html.parser')
        ja_soup=BeautifulSoup(ja_html, 'html.parser')
        en_text=extract_main_text(en_soup)
        ja_text=extract_main_text(ja_soup)
        if is_not_found(en_text) or is_not_found(ja_text):
            print('Not Found: ', m['id'], file=sys.stderr)
            continue
        if len(en_text)==0 or len(ja_text)==0:
            print('None: ', m['id'], file=sys.stderr)
            continue
        if len(en_text)!=len(ja_text):
            print('不一致: ', m['id'], len(en_text), len(ja_text), file=sys.stderr)
            continue
        if not check_num_newlines(en_text, ja_text):
            print('改行数不一致: ', m['id'], file=sys.stderr)
            continue
        ja_date=extract_date(BeautifulSoup(ja_html, 'html.parser'))
        if not ja_date:
            print('日付取得失敗: ', m['id'], file=sys.stderr)
            continue
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

