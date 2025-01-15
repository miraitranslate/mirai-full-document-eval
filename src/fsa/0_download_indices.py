import argparse
import hashlib
import os
import re
import sys
import time
import urllib

import requests

parser=argparse.ArgumentParser()
parser.add_argument('oldest_yearmonth', type=int)
parser.add_argument('output_tsv')
parser.add_argument('--html_directory', default='html')
parser.add_argument('--base_uri', default='https://www.fsa.go.jp/')
parser.add_argument('--index_uri', default='https://www.fsa.go.jp/en/news/index.html')
parser.add_argument('--index_file', default='index.html')
parser.add_argument('--delay', type=float, default=1.0)
args=parser.parse_args()

oldest_yearmonth=args.oldest_yearmonth
output_tsv=args.output_tsv
html_directory=args.html_directory
base_uri=args.base_uri
index_uri=args.index_uri
index_file=args.index_file
delay=args.delay

DOCIDPREFIX='fsa_'

if not os.path.exists(index_file):
    response = requests.get(index_uri)
    response.encoding = response.apparent_encoding
    # ダウンロードをやり直したくないので書き出す
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(response.text)
        print(f'Saved to {index_file}', file=sys.stderr)

tsv=[]
with open('index.html', encoding='utf-8') as f:
    for line in f:
        m = re.search(r'<a href="(.+?)"', line)
        if m:
            en_uri=urllib.parse.urljoin(base_uri, m.group(1))
            doc_id=DOCIDPREFIX+hashlib.md5(en_uri.encode()).hexdigest()[:8]
            yearmonth_exists=re.search(r'(20\d{6})(-\d+)?.html', en_uri)
            if yearmonth_exists:
                yearmonth=int(yearmonth_exists.group(1)[:6])
                if yearmonth>=oldest_yearmonth:
                    print(f'Extracted: {en_uri}', file=sys.stderr)
                    en_filename=os.path.join(html_directory, en_uri.split('/')[-1].split('.')[0]+'.en')
                    ja_filename=os.path.join(html_directory, en_uri.split('/')[-1].split('.')[0]+'.ja')
                    if not os.path.exists(en_filename):
                        response = requests.get(en_uri)
                        response.encoding = response.apparent_encoding
                        with open(en_filename, 'w', encoding='utf-8') as f:
                            f.write(response.text)
                            print(f'Saved to {en_filename}', file=sys.stderr)
                    with open(en_filename) as f:
                        for line in f:
                            m = re.search(r'<a target="_blank" href="(.+?)">Japanese(<img.+?)?</a>', line) # relative uri
                            if m:
                                ja_uri=urllib.parse.urljoin(base_uri, m.group(1))
                                print(f'Extracted: {ja_uri}', file=sys.stderr)
                                if not os.path.exists(ja_filename):
                                    response = requests.get(ja_uri)
                                    response.encoding = response.apparent_encoding
                                    with open(ja_filename, 'w', encoding='utf-8') as f:
                                        f.write(response.text)
                                        print(f'Saved to {ja_filename}', file=sys.stderr)
                                    time.sleep(delay)
                                    tsv.append("\t".join([doc_id, os.path.basename(ja_filename), os.path.basename(en_filename), ja_uri, en_uri]))
                                    break
with open(output_tsv, 'w') as f:
    print('doc_id\tja_filename\ten_filename\tja_uri\ten_uri', file=f)
    f.write('\n'.join(tsv))
