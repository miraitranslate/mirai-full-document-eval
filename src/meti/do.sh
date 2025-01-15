oldest=202410
html_dir=html
tsv_dir=tsv
json_dir=json

mkdir -p $html_dir
mkdir -p $tsv_dir
mkdir -p $json_dir

newest=`date +%Y%m`

python3 0_download_indices.py $oldest ${tsv_dir%/}/$oldest-$newest.tsv --html_directory $html_dir
python3 1_extract_body.py ${tsv_dir%/}/$oldest-$newest.tsv ${json_dir%/}/$oldest-$newest.json --html_directory $html_dir

