#!/bin/bash

html_dir=html
tsv_dir=tsv
json_dir=json

mkdir -p "$html_dir" "$tsv_dir" "$json_dir"
newest=${TARGET_YEARMONTH:-$(date -u -d 'last month' +%Y%m 2>/dev/null || date -u -v-1m +%Y%m)}
if [ -n "${MOF_OLDEST:-}" ]; then
  oldest=$MOF_OLDEST
else
  y=$(( newest / 100 )); m=$(( newest % 100 - 1 ))
  if [ "$m" -le 0 ]; then m=$(( m + 12 )); y=$(( y - 1 )); fi
  oldest=$(printf '%d%02d' "$y" "$m")
fi

if [ "$oldest" -gt "$newest" ]; then
  echo "mof/do.sh: 起点 ($oldest) が対象月 ($newest) より後" >&2
  exit 2
fi

rm -f "${json_dir%/}"/*.json "${tsv_dir%/}"/*.tsv

echo "Oldest: $oldest"
echo "Newest: $newest"

python3 0_download.py "$oldest" "$newest" "${tsv_dir%/}/$oldest-$newest.tsv" "$html_dir"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "mof/do.sh: 取得段が exit $rc。抽出は行わない" >&2
  exit "$rc"
fi
python3 1_extract_body.py "${tsv_dir%/}/$oldest-$newest.tsv" "${json_dir%/}/$oldest-$newest.json" --html_directory "$html_dir"
