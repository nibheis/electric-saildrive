#!/bin/bash

CAN=can0

function can_status() {
	if [[ $(ip addr show ${CAN} | grep -c ' DOWN ') -eq 1 ]]; then
		# DOWN
		echo "Interface ${CAN}: DOWN"
		return 1
	else
		if [[ $(ip addr show ${CAN} | grep -c ' UP ') -eq 1 ]]; then
			# UP
			echo "Interface ${CAN}: UP"
			return 0
		else
			echo "Interface ${CAN}: ??"
			return 2
		fi
	fi
}

function can_start() {
	can_status
	cs=${?}
	if [[ ${cs} -eq 1 ]]; then
		# J1939 => 250000 kbps
		sudo ip link set ${CAN} type can bitrate 250000
		sudo ip link set up ${CAN}
	fi
	can_status
	return $?
}

can_start
exit $?

# EOF
