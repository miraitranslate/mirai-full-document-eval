import argparse
import glob
import hashlib
import os
import re
import sys
import time
import urllib

import requests

parser=argparse.ArgumentParser()
parser.add_argument('oldest_yearmonth', type=int)
parser.add_argument('newest_yearmonth', type=int)
parser.add_argument('output_tsv')
parser.add_argument('--html_directory', default='html')
parser.add_argument('--base_uri', default='https://www.meti.go.jp/')
parser.add_argument('--index_uri', default='https://www.meti.go.jp/english/press/nBackIssue')
parser.add_argument('--index_directory', default='indices')
parser.add_argument('--delay', type=float, default=1.0)
args=parser.parse_args()

base_uri=args.base_uri
index_uri_base=args.index_uri
index_dir=args.index_directory
html_dir=args.html_directory
tsv_path=args.output_tsv

from_yearmonth=args.oldest_yearmonth
to_yearmonth=args.newest_yearmonth

user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'

for yearmonth in range(from_yearmonth, to_yearmonth+1):
    if yearmonth%100==13:
        yearmonth+=88
    index_uri=f'{index_uri_base}{yearmonth}.html'
    index_path=os.path.join(index_dir, f'{yearmonth}.html')
    if not os.path.exists(index_path):
        print(f'downloading {index_uri} to {index_path}', file=sys.stderr)
        with open(index_path, 'w') as f:
            response=requests.get(index_uri, headers={'User-Agent': user_agent})
            response.encoding=response.apparent_encoding
            f.write(response.text)
    time.sleep(args.delay)

# extract en_uri from indices
metadata=[]
metadata.append("doc_id\tja_file\ten_file\tja_URI\ten_URI")
for index_path in glob.glob(os.path.join(index_dir, '*.html')):
    print(f'processing {index_path}', file=sys.stderr)
    with open(index_path) as f:
        index_html=f.read()
    for m in re.finditer(r'<a href="(/english/press/.+?)"', index_html):
        en_uri=urllib.parse.urljoin(base_uri, m.group(1))
        id='meti_'+hashlib.md5(en_uri.encode()).hexdigest()[:8]
        # skip if filename does not contain digits
        if not re.search(r'\d', en_uri):
            continue
        # download en_html
        en_file=f'{id}.en.html'
        en_path=os.path.join(html_dir, en_file)
        print(f'processing {en_uri} > {en_path}', file=sys.stderr)
        if not os.path.exists(en_path):
            print(f'downloading {en_uri} to {en_path}', file=sys.stderr)
            with open(en_path, 'w') as f:
                response=requests.get(en_uri, headers={'User-Agent': user_agent})
                response.encoding=response.apparent_encoding
                f.write(response.text)
            # find a link to ja_html in en_html such as <a href="/press/2024/06/20240620002/20240620002.html">Japanese</a>
            with open(en_path) as f:
                en_html=f.read()
            m=re.search(r'<a href="(/press/.*?\.html)">Japanese</a>', en_html)
            if m:
                ja_uri=urllib.parse.urljoin(base_uri, m.group(1))
                # download ja_html
                ja_file=f'{id}.ja.html'
                ja_path=os.path.join(html_dir, ja_file)
                if not os.path.exists(ja_path):
                    print(f'downloading {ja_uri} to {ja_path}', file=sys.stderr)
                    with open(ja_path, 'w') as f:
                        response=requests.get(ja_uri, headers={'User-Agent': user_agent})
                        response.encoding=response.apparent_encoding
                        f.write(response.text)
                    metadata.append(f'{id}\t{ja_file}\t{en_file}\t{ja_uri}\t{en_uri}')
        time.sleep(args.delay)
with open(tsv_path, 'w') as f:
    f.write('\n'.join(metadata))
