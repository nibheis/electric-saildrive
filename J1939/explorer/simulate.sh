#!/bin/bash

can_interface="can0"

messages="18F00400#FFFFFFFF1027FFFF 18FEEE00#3FFFE026FFFFFFFF 18FEE500#FF2C010000FFFFFF 18EAFFFE#E5FE00"

while [[ true ]]; do
	echo -n '.'
	for msg in $(echo ${messages}); do
		cansend ${can_interface} ${msg}
		sleep 1
	done
done

# EOF
