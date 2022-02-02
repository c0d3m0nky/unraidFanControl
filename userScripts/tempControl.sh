checkInterval=5s
#sdc WD 500gb
#sde WD 3tb
#sdf SG 4tb
array=("/dev/sdc" "/dev/sde" "/dev/sdf")
arrayFans=("CHA1" "CHA2")
arrayMinTemps=(30 35 40 45 50)
arrayPwms=(127 165 175 200 254)

ssds=("/dev/sdb" "/dev/sdd")
ssdFans=("CPU2")
ssdMinTemps=(30 35 40 45)
ssdPwms=(127 165 190 254)

sysFans=("CHA3")
sysTemps=(40 50 60 70 75)
sysPwms=(127 165 180 200 254)

# ./fans.sh set CHA1 127
# ./fans.sh set CHA2 127
# ./fans.sh set CHA3 127
# ./fans.sh set CPU2 127
# ./fans.sh ctrl CHA1
# ./fans.sh ctrl CHA2
# ./fans.sh ctrl CHA3
# ./fans.sh ctrl CPU2

function log(){
	printf "$1\n"
}

function DriveTemp(){
	local drive=$1
	local sleeping=`hdparm -C $drive | grep -c standby`
	if [ $sleeping == "0" ]; then
		local temp=`smartctl -d ata -A $drive | grep -m 1 -i Temperature_Celsius | awk '{print $10}'`

		log "$drive at $temp celcius"
	    return $(( $temp + 0 ))
	else
		log "$drive is asleep"
		return 0
	fi
}

function SetFanSpeed(){
	temps=$1
	pwms=$2
	temp=$3
	onTemp=${temps[0]}

	if (( $temp < $onTemp )); then
		log "Shut off fans $fans"
	else
		pwm=254
		for i in "${!temps[@]}"; do 
			t=${temps[$i]}
			if (( $temp < $t )); then 
		  		i=$(expr $i-1)
		  		pwm=${pwms[$i]}
			fi
		done

  		for f in "${!fans[@]}"; do 
  			log "Set $pwm to $fans"
  		done
	fi
}

function SetDriveFans(){
	local drives=$1
	local temps=$2
	local pwms=$3
	local fans=$4
	local onTemp=${temps[0]}
	local maxTemp=0
	local temp=0

	for d in ${drives[@]}
	do
		DriveTemp $d
		temp=$?
		if(( $temp > $maxTemp )); then
			maxTemp=$temp
		fi
	done

	SetFanSpeed $temps $pwms $maxTemp
}

function run(){
	log "Setting Array fans"
	SetDriveFans array arrayMinTemps arrayPwms arrayFans
	# log "Setting SSD fans"
	# SetDriveFans $ssds $ssdMinTemps $ssdPwms $ssdFans
	# log "Setting GPU/CPU fans"
	# temps=$(sensors | grep -E '(MB|CPU) Temp:')
	# mobot=$(echo $temps | grep -E MB | awk '{print $3}') | grep -Eo '[0-9]{2,}'
	# cput=$(echo $temps | grep -E CPU | awk '{print $3}') | grep -Eo '[0-9]{2,}'

	# log "MB $mobot"
	# log "CPU $cput"
}

while : 
do
	run
	sleep $checkInterval
done