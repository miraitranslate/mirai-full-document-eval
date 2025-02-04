#!/bin/bash

oldest=202410
num_months=3
index_dir=indices
html_en_dir=en
html_ja_dir=ja
tsv_dir=tsv
json_dir=json

mkdir -p "$index_dir"
mkdir -p "$html_en_dir"
mkdir -p "$html_ja_dir"
mkdir -p "$tsv_dir"
mkdir -p "$json_dir"

newest=$(date +"%Y%m")

echo "Oldest: $oldest"
echo "Newest: $newest"
for primeminister in 103 # 102_ishiba 101_kishida 100_kishida 99_suga 98_abe 
do
    ./0_download_indices.sh "$index_dir" "$primeminister" "$oldest" "$num_months"
done
python 1_extract_uris.py "${index_dir%/}" > URIs.txt
./2_download_en.sh URIs.txt "$html_en_dir"
python 3_extract_body.py "$html_en_dir" "$html_ja_dir" "${json_dir%/}/${oldest}-${newest}.json"
