#!/bin/bash

# usage: bash 0_download_indices.sh [directory] [primeminister] [oldest_month] [num_months]
directory=$1
primeminister=$2
oldest_month=$3
num_months=$4
baseURI="https://japan.kantei.go.jp/${primeminister}/actions/"

# OSの判別（Linuxなら GNU date, macOSなら BSD date）
if date --version >/dev/null 2>&1; then
    DATE_CMD="gnu"
else
    DATE_CMD="bsd"
fi

months=()
for i in $(seq 0 "$num_months"); do
    if [ "$DATE_CMD" = "gnu" ]; then
        months+=("$(date -d "${oldest_month}01 +${i} month" +%Y%m)")
    else
        months+=("$(date -v+${i}m -j -f "%Y%m%d" "${oldest_month}01" +"%Y%m")")
    fi
done

for i in "${months[@]}"; do
    output_file_name="${directory%/}/${primeminister}_${i}.html"
    uri="${baseURI}${i}/index.html"
    # download the page
    curl -A "Mozilla/5.0 (Windows NT 10.0; Win16; 8086) Chrome Firefox" -o "$output_file_name" "$uri"
    sleep 2s
done
