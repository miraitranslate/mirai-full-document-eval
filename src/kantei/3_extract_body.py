import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import sys
import time

from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin

BASE_JA_URI='https://www.kantei.go.jp/'
BASE_EN_URI='https://japan.kantei.go.jp/'
RE_URI=re.compile('www.kantei.go.jp/jp/')

def get_body_en(soup, v):
    if v=='new':
        # First, extract the div with the class "section" and "has-detail-more"
        div=soup.find('div', class_='section has-detail-more')
    elif v=='old':
        # First, extract the div with the id "format"
        div=soup.find('div', id='format')
    else:
        sys.exit('Error: version is neither "new" nor "old"')
    if div is None:
        return None
    # Then, remove the div with the class "aly_tx_right" if it EXISTS
    div_aly_tx_right=div.find('div', class_='aly_tx_right')
    if div_aly_tx_right:
        div_aly_tx_right.decompose()
    # If it exists, remove p aligned right
    for p in div.find_all('p', align='right'):
        p.decompose()
    # if button exists, remove it
    for button in div.find_all('button'):
        button.decompose()
    text=div.get_text()
    text=text.strip()
    text=text.replace('\xc2\xa0', ' ')
    text=re.sub(r'\n\s+\n', '\n\n', text)
    paragraphs=text.split('\n\n')
    paragraphs=remove_empty_paragraphs(paragraphs)
    return paragraphs

def get_self_URI(soup, v):
    a=soup.find('meta', property='og:url')
    if a:
        return a.get('content', None)
    return None

def get_japanese_URI(soup, v):
    # Extract URI in href in <a>, which contains "www.kantei.go.jp/jp/"
    a=soup.find('a', href=RE_URI)
    if a is None:
        return None
    URI=a['href']
    # if the URI is relative, convert it to absolute
    if not URI.startswith('http'):
        URI=urljoin(BASE_JA_URI, URI)
    return URI

def get_body_ja(soup):
    div=soup.find('div', class_='section')
    if div is None:
        return None
    paragraphs=[]
    for p in div.find_all('p'):
        text=p.get_text().strip().replace('\t', '')
        # there are sometimes paragraphs separated by "\n　"
        paragraphs_in_paragraph=text.split('\n　')
        paragraphs_in_paragraph=remove_empty_paragraphs(paragraphs_in_paragraph)
        paragraphs.extend(paragraphs_in_paragraph)
    return paragraphs

def get_date_ja(soup):
    # get the span with the class "date"
    span=soup.find('span', class_='date')
    str_date=span.get_text()
    return convert_str_date_into_datetime(str_date)

def convert_str_date_into_datetime(str_date):
    # extract date in Japanese format
    match=re.search(r'(平成|令和)(\d{1,2}|元)年(\d{1,2})月(\d{1,2})日', str_date)
    if match:
        era=match.group(1)
        year=int(match.group(2) if match.group(2)!='元' else 1)
        month=int(match.group(3))
        day=int(match.group(4))
        if era=='平成':
            year+=1988
        elif era=='令和':
            year+=2018
        return datetime.date(year, month, day)
    else:
        return None

def get_version(soup):
    # if div with the id "top" exists, it is "new" version; if "header" exists, it is "old" version
    if soup.find('div', id='top'):
        return 'new'
    else:
        return 'old'

def download_and_save_html(url, output_path):
    response=requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 12.0; Win32; x86) AppleWebKit/934.78 (KHTML, like Gecko) Chrome/315.0.0.0 Safari/779.68 Edge/43.29855'})
    response.encoding=response.apparent_encoding
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(response.text)

def remove_empty_paragraphs(list_para):
    return [para.strip() for para in list_para if para.strip()!='']

def check_num_newlines(paragraphs0, paragraphs1):
    # Count the number of lines in each paragraph.
    # If in one paragraph the number of lines is different from the other, return False.
    for p0, p1 in zip(paragraphs0, paragraphs1):
        if p0.count('\n') != p1.count('\n'):
            return False
    return True

def generate_uid(URI):
    return hashlib.md5(URI.encode()).hexdigest()[:8]

def main(args):
    en_directory=args.en_directory
    ja_directory=args.ja_directory
    output_json=args.output_json
    all_data=[]
    
    path_list=glob.glob(os.path.join(en_directory, '*'))
    N=len(path_list)
    c=0
    IDs={}
    for en_path in path_list:
        c+=1
        print(f'({c}/{N}); 処理開始 {en_path}', flush=True, file=sys.stderr)
        uid=f'kantei_{generate_uid(en_path)}'
        if uid in IDs:
            sys.exit(f'Error: 重複したID: {uid}')
        IDs[uid]=1
        data={
            'id': uid, # 8文字のハッシュ値
            'en_URI': None,
            'ja_URI': None,
            'en_body': None,
            'ja_body': None,
            'ja_date': None 
        }
        soup=BeautifulSoup(open(en_path), 'html.parser')
        template_version=get_version(soup)
        data['en_URI']=get_self_URI(soup, template_version)
        data['en_body']=get_body_en(soup, template_version)
        data['ja_URI']=get_japanese_URI(soup, template_version)
        
        # skip if either en_URI, ja_URI or en_body is None:
        if data['en_URI'] is None or data['ja_URI'] is None or data['en_body'] is None:
            print(f'en_URI, ja_URI, en_bodyのいずれかがNone: {en_path}')
            continue
        # download the Japanese page
        ja_basename=data['en_URI'].replace(BASE_EN_URI, '').replace('/', '--').replace('.html', '')
        ja_path=os.path.join(ja_directory, ja_basename+'.html')
        # if it already exists, skip
        if os.path.exists(ja_path):
            pass
        else:
            print(f'ダウンロードする: {ja_path}')
            download_and_save_html(data['ja_URI'], ja_path)
            time.sleep(1)
        ja_soup=BeautifulSoup(open(ja_path), 'html.parser')
        data['ja_body']=get_body_ja(ja_soup)
        if data['ja_body'] is None:
            print(f'Error: ja_bodyがNone: {ja_path}', file=sys.stderr)
            continue
        data['ja_date']=get_date_ja(ja_soup).isoformat()
        if len(data['en_body'])!=len(data['ja_body']):
            print(f'段落数不一致：{en_path} と {ja_path}', file=sys.stderr)
            continue
        if not check_num_newlines(data['en_body'], data['ja_body']):
            print('改行数不一致: ', en_path, file=sys.stderr)
            continue
        all_data.append(data)
    with open(output_json, 'w') as f:
        json.dump(all_data, f, ensure_ascii=False, indent="\t")
    # print the number of data
    print(len(all_data), file=sys.stderr)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('en_directory')
    parser.add_argument('ja_directory')
    parser.add_argument('output_json')
    args=parser.parse_args()
    main()
