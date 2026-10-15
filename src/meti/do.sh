#!/bin/bash

html_dir=html
tsv_dir=tsv
json_dir=json

mkdir -p "$html_dir" "$tsv_dir" "$json_dir"

newest=${TARGET_YEARMONTH:-$(date -u -d 'last month' +%Y%m 2>/dev/null || date -u -v-1m +%Y%m)}
if [ -n "${METI_OLDEST:-}" ]; then
  oldest=$METI_OLDEST
else
  y=$(( newest / 100 )); m=$(( newest % 100 - 2 ))
  if [ "$m" -le 0 ]; then m=$(( m + 12 )); y=$(( y - 1 )); fi
  oldest=$(printf '%d%02d' "$y" "$m")
fi

rm -f "${json_dir%/}"/*.json

echo "Oldest: $oldest"
echo "Newest: $newest"

python3 0_download_indices.py "$oldest" "$newest" "${tsv_dir%/}/$oldest-$newest.tsv" --html_directory "$html_dir" --skip-in ../../data.json
rc_dl=$?
if [ "$rc_dl" -eq 5 ]; then
  echo "meti/do.sh: ダウンロード段が exit 5（取得失敗が続いたため停止）。取得済み分だけで抽出して終了する。時間を置いて再実行" >&2
elif [ "$rc_dl" -ne 0 ]; then
  echo "meti/do.sh: ダウンロード段が exit $rc_dl（スクリプトの異常）。抽出は行わない" >&2
  exit "$rc_dl"
fi
python3 1_extract_body.py "${tsv_dir%/}/$oldest-$newest.tsv" "${json_dir%/}/$oldest-$newest.json" --html_directory "$html_dir"
rc_ex=$?
if [ "$rc_ex" -ne 0 ]; then exit "$rc_ex"; fi
exit "$rc_dl"
