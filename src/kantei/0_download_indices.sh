# usage: bash 0_download_indices.sh [directory] [primeminister]
directory=$1
primeminister=$2
oldest_manth=$3
num_months=$4
baseURI=https://japan.kantei.go.jp/${primeminister}/actions/

months=()
for i in `seq 0 $num_months`
do
    months+=`date -d "${oldest_manth}01 +${i} month" +%Y%m`
done

for i in ${months[@]}
do
    output_file_name="${directory%/}/${primeminister}_${i}.html"
    uri=${baseURI}${i}/index.html
    # download the page
    wget -U "Mozilla/5.0 (Windows NT 10.0; Win16; 8086) Chrome Firefox" -O $output_dir $uri
    sleep 2s
done
