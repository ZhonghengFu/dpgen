#!/bin/bash

source env.sh

targets=`seq 0.93 0.005 1.04`

script_file=in.tmp.$$
out_file=tmp.out.$$
for ii in $targets
do
    sed "s/SCALE/$ii/g" in.hcp > $script_file
    $lmp_cmd -i $script_file &> $out_file
    epa=`grep ENER_PER_ATOM $out_file | awk '{print $2}'`
    epv=`grep VOLM_PER_ATOM $out_file | awk '{print $2}'`
    coa=`grep COA $out_file | awk '{print $2}'`
    echo $epv $epa $coa
done

rm -f $script_file $out_file