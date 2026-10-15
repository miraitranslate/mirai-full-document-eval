#!/bin/bash

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

newest=${TARGET_YEARMONTH:-$(date -u -d 'last month' +%Y%m 2>/dev/null || date -u -v-1m +%Y%m)}
if [ -n "${KANTEI_OLDEST:-}" ]; then
  oldest=$KANTEI_OLDEST
else
  y=$(( newest / 100 )); m=$(( newest % 100 - 1 ))
  if [ "$m" -le 0 ]; then m=$(( m + 12 )); y=$(( y - 1 )); fi
  oldest=$(printf '%d%02d' "$y" "$m")
fi

rm -f "${json_dir%/}"/*.json

if ! command -v wget >/dev/null 2>&1; then
  echo "kantei/do.sh: wget が見つからない（brew install wget）" >&2
  exit 3
fi

echo "Oldest: $oldest"
echo "Newest: $newest"
num_months=$(( (newest / 100 - oldest / 100) * 12 + (newest % 100 - oldest % 100) ))
if [ "$num_months" -lt 0 ]; then
  echo "kantei/do.sh: TARGET_YEARMONTH ($newest) が oldest ($oldest) より前" >&2
  exit 2
fi

UA="Mozilla/5.0 (Windows NT 10.0; Win16; 8086) Chrome Firefox"
known_pms="102_ishiba 103 104 105"
current_pms=$(curl -s -A "$UA" https://japan.kantei.go.jp/ | grep -oE '/[0-9]{3}/actions/' | tr -d '/' | sed 's/actions//' | sort -u | tr '\n' ' ')
for primeminister in $(printf '%s\n' $known_pms $current_pms | sort -u)
do
    ./0_download_indices.sh "$index_dir" "$primeminister" "$oldest" "$num_months"
done

python3 1_extract_uris.py "${index_dir%/}" --oldest "$oldest" > URIs.txt
python3 1_extract_uris.py "${index_dir%/}" --oldest "$oldest" --exclude-downloaded "$html_en_dir" > URIs.new.txt

if ! grep -q "/actions/${newest}/" URIs.txt; then
  echo "kantei/do.sh: ${newest} の index に記事リンクが無い（首相コード ${known_pms} ${current_pms}）" >&2
  exit 4
fi

if [ -s URIs.new.txt ]; then
    ./2_download_en.sh URIs.new.txt "$html_en_dir"
else
    echo "kantei/do.sh: 新規記事なし（全 URI 取得済み）"
fi

python3 3_extract_body.py "$html_en_dir" "$html_ja_dir" "${json_dir%/}/${oldest}-${newest}.json" --uris URIs.txt
