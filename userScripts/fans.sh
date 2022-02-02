controlRoot=/sys/devices/platform/nct6775.656/hwmon/hwmon1/
sysFans=(1 2 3 4 5 6)
pwmSet=(1 2 3 4 5 6)
commNames=("CHA3" "CPU1" "CPU2" "CHA1" "CHA2" "CHST")
CPU1=2
CPU2=3
CHA1=4
CHA2=5
CHA3=1
CHST=6

function SysToCommName() {
	for i in "${!sysFans[@]}"; do 
		sn=${sysFans[$i]}
		if [[ $sn == $1 ]]; then 
	  		echo -n ${commNames[$i]}
			return
		fi
	done
	echo -n "fan$1"
}

function SysToPwmSet() {
	for i in "${!sysFans[@]}"; do 
		sn=${sysFans[$i]}
		if [[ $sn == $1 ]]; then 
	  		echo -n ${pwmSet[$i]}
			return
		fi
	done
	echo -n "-1"
}

function CommNameToPwm() {
	for i in "${!commNames[@]}"; do 
		cn=${commNames[$i]}
		if [[ $cn == $1 ]]; then 
	  		echo -n ${pwmSet[$i]}
			return
		fi
	done
	echo -n ""
}

function CommNameToSys() {
	for i in "${!commNames[@]}"; do 
		cn=${commNames[$i]}
		if [[ $cn == $1 ]]; then 
	  		echo -n ${sysFans[$i]}
			return
		fi
	done
	echo -n ""
}

function PwmEnabled(){
	pn=$(SysToPwmSet $1)
	pnef=${controlRoot}pwm${pn}_enable
	
	echo $(cat $pnef)
}

function ControlEnabled(){
	pne=$(PwmEnabled $1)

	if [[ $pne == "1" ]]; then
		echo 1
	else
		echo 0
	fi	
}

function _Set(){
	cn=$1
	pwm=$2
	sn=$(CommNameToSys $cn)
	
	if [[ $sn == "" ]]; then
		echo "Invalid fan name $cn"
		exit 0
	fi

	pn=$(SysToPwmSet $sn)
	
	if [[ $pn == "-1" ]]; then
		echo "Fan $cn not configured"
		exit 0
	fi
	
	if [[ $(ControlEnabled $sn) != "1" ]]; then
		echo "Fan $cn control disabled"
		exit 0
	fi
	
	pwmf=${controlRoot}pwm${pn}

	if (( $pwm > -1 )) && (( $pwm < 255 )); then
		# echo "Set $cn :: $sn :: $pn -> $pwm ($pwmf)"
		echo $pwm > $pwmf
	else
		echo "Invalid pwm $pwm"
	fi
}

case $1 in
	ls)
		for f in ${sysFans[@]}
		do
			sn="fan${f}_input"
			cn=$(SysToCommName $f)
			pn=$(SysToPwmSet $f)
			rpm=$(cat $controlRoot$sn)
			pwm=$(cat ${controlRoot}pwm${pn})
			enb=$(PwmEnabled $f)
			printf "$f $cn \t $enb \t $pwm \t $rpm\n"
		done
		;;
	lss)
		for i in "${!sysFans[@]}"; do 
			sn=${sysFans[$i]}
			cn=$(SysToCommName $sn)
			echo "$i fan$sn -> $cn"
		done
		;;
	set)
		_Set $2 $3
		;;
	ctrl)
		pn=$(CommNameToPwm $2)
		pnef=${controlRoot}pwm${pn}_enable
		pwmf=${controlRoot}pwm${pn}
		cset=$(cat $pwmf)

		if (( $cset > 254 )); then
			echo 254 > $pwmf
		fi

		echo 1 > $pnef
		# echo $pnef
		;;
	*)
		echo "Bad cmd"
esac
