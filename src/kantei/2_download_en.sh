list=$1
output_dir=$2
wget -U "Mozilla/5.0 (Windows NT 10.0; Win16; 8086) Chrome Firefox" -i $list -P $output_dir --wait=3 --random-wait
