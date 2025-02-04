#!/bin/bash

oldest=202410
html_dir=html
tsv_dir=tsv
json_dir=json

mkdir -p "$html_dir" "$tsv_dir" "$json_dir"
newest=$(date +"%Y%m")

echo "Oldest: $oldest"
echo "Newest: $newest"

python3 0_download.py "$oldest" "$newest" "${tsv_dir%/}/$oldest-$newest.tsv" "$html_dir"
python3 1_extract_body.py "${tsv_dir%/}/$oldest-$newest.tsv" "${json_dir%/}/$oldest-$newest.json" --html_directory "$html_dir"
