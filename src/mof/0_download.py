import argparse
import datetime
import hashlib
import os
import re
import sys
import time
import urllib

import requests

def add_a_month(date):
    # date is a datetime object
    year=date.year
    month=date.month
    if month==12:
        year+=1
        month=1
    else:
        month+=1
    return datetime.datetime(year, month, 1)

def main(args):
    from_yearmonth=datetime.datetime.strptime(args.from_yearmonth, '%Y%m')
    to_yearmonth=datetime.datetime.strptime(args.to_yearmonth, '%Y%m')
    output_tsv=args.output_tsv
    html_dir=args.html_dir
    index_URI_template='https://www.mof.go.jp/english/public_relations/whats_new/{yearmonth}.html'

    yearmonths=[]
    current=from_yearmonth
    while current<=to_yearmonth:
        yearmonths.append(current.strftime('%Y%m'))
        current=add_a_month(current)

    for yearmonth in yearmonths:
        index_URI=index_URI_template.format(yearmonth=yearmonth)
        r=requests.get(index_URI)
        with open('index_'+yearmonth+'.html', 'w') as f:
            f.write(r.text)
    
    tsv=['id\tja_file\ten_file\tja_URI\ten_URI']
    for yearmonth in yearmonths:
        with open('index_'+yearmonth+'.html') as f:
            html=f.read()
        for l in html.split('\n'):
            if '<li class="information-item">' in l:
                if 'JGBs' in l or 'PRI' in l or 'Trade Statistics' in l or 'FILP' in l or 'Exchequer' in l or 'Currency' in l or 'Balance of' in l or 'International Reserves/Foreign Currency Liquidity' in l:
                    continue
                m=re.search(r'<a href="(.+?)"', l)
                if m:
                    en_URI=m.group(1)
                    if not en_URI.endswith('.htm') and not en_URI.endswith('.html'):
                        continue
                else:
                    continue
                en_URI=urllib.parse.urljoin(index_URI, en_URI)
                doc_id=hashlib.md5(en_URI.encode()).hexdigest()[:8]
                print(en_URI, file=sys.stderr)
                r=requests.get(en_URI)
                with open(os.path.join(html_dir, 'mof_'+doc_id+'.en.html'), 'w') as f:
                    f.write(r.text)
                for ll in r.text.split('\n'):
                    m=re.search(r'<div class="text-right"><a href="(.+?)" class="button -arrow-r -sm">Japanese</a></div>', ll)
                    if m:
                        ja_URI=urllib.parse.urljoin(en_URI, m.group(1))
                        print(ja_URI, file=sys.stderr)
                        r=requests.get(ja_URI)
                        with open(os.path.join(html_dir, 'mof_'+doc_id+'.ja.html'), 'w') as f:
                            f.write(r.text)
                        tsv.append('\t'.join([doc_id, 'mof_'+doc_id+'.ja.html', 'mof_'+doc_id+'.en.html', ja_URI, en_URI]))
                        time.sleep(1)
                        break
    with open(output_tsv, 'w') as f:
        f.write('\n'.join(tsv))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('from_yearmonth', type=str)
    parser.add_argument('to_yearmonth', type=str)
    parser.add_argument('output_tsv', type=str)
    parser.add_argument('html_dir', type=str)
    args=parser.parse_args()
    main(args)