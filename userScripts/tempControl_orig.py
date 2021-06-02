import os
import subprocess
import time
import re
import datetime

#region Infra

check_interval = 60
trace_log = False
fanset_log = True
gpu_temp_file = './gputemp.log'
fans_shell = '/mnt/user/projects/fanControl/fans.sh'

def shell(cmd, check = False):
	res = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True, check=check)
	return res.stdout.decode('utf-8').strip()

def logts():
	return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def log_fanset(msg):
	if fanset_log :
		print(f'{logts()}\tFANSET\n<-------------\n{msg}\n------------->')

def trace(msg):
	if trace_log :
		print(f'{logts()}\tTRACE\t{msg}')

def log(msg):
	print(f'{logts()}\tLOG\t{msg}')

def err(msg, e = None):
	if e :		
		print(f'{logts()}\tERROR\t{msg}\n\n{e}\n\n')
	else:
		print(f'{logts()}\tERROR\t{msg}')

# Lookup data class
class DriveGroup:
	def __init__(self, drives, fans, temps):
		self.drives = drives
		self.fans = fans
		self.temps = temps

#sdc WD 500gb
#sde WD 3tb
#sdf SG 4tb
array = DriveGroup(["/dev/sdc", "/dev/sde", "/dev/sdf"], ["CHA1", "CHA2"], [[30,127], [35,165], [40,175], [45,200], [50,254]])
ssds = DriveGroup(["/dev/sdb", "/dev/sdd"], ["CPU2"], [[30,127], [35,165], [40,190], [45,254]])
sys_fans=["CHA3"]
sys_temps=[[40,127], [50,165], [60,180], [70,200], [75,254]]

#endregion

#

#	Type hinting, just like typescript

#

# Look into iterTools
def set_fan_speed(sensor_temp, temps, fans):
	on_temp = temps[0][0]

	if sensor_temp < on_temp :
		log_fanset(f'Shut off fans {fans}')
		for f in fans :
			shell(f'{fans_shell} set {f} 0')
	else:
		pwm=254
		for i, t in enumerate(temps) :
			t = temps[i][0]
			if sensor_temp < t :
				pwm = temps[i-1][1]
				break

		log_fanset(f'Set {fans} to {pwm}')
		for f in fans :
			shell(f'{fans_shell} set {f} {pwm}')

def drive_temp(drive):
	sleeping = shell(f'hdparm -C {drive} | grep -c standby')
	if sleeping == "0":
		temp = shell(f"smartctl -d ata -A {drive} | grep -m 1 -Ei '(Temperature_Celsius|Airflow_Temperature_Cel)' | awk '{{print $10}}'")

		if not temp.isnumeric() :
			err(f'Failed to retrieve temp for {drive}')
			return -1

		trace(f'{drive} at {temp} celcius')
		return int(temp)

	trace(f'{drive} is asleep')
	return 0

def set_drive_fans(drives) :
	max_temp=0

	for d in drives.drives :
		temp = drive_temp(d)
		if temp > max_temp :
			max_temp = temp

	set_fan_speed(max_temp, drives.temps, drives.fans)

rx_mobot = re.compile("MB Temp: +.(\d{2,})\.")
rx_cput = re.compile("CPU Temp: +.(\d{2,})\.")
rx_gput = re.compile("(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\d+)")
gpu_log_time_delta = datetime.timedelta(minutes=-5)

def set_sys_fans() :
	temps = shell('sensors | grep -E "(MB|CPU) Temp:"')
	trace(f'Sys temps\n\n\t---\n\n{temps}\n\n\t---\n')
	
	ms = rx_mobot.match(temps)

	if ms and ms.group(1).isnumeric() :
		mobot = int(ms.group(1))
		trace(f'MB: {mobot}')
	else:
		err('Failed to retrieve temp for motherboard')
	
	ms = rx_cput.search(temps)

	if ms and ms.group(1).isnumeric():
		cput = int(ms.group(1))
		trace(f'CPU: {cput}')
	else:
		err('Failed to retrieve temp for cpu')

	gput = -1
	if os.path.isfile(gpu_temp_file) :
		try:
			# This is bad, only works if there's more than 1 line and log doesn't have trailing linebreak, look for package to do better
			# Fuck this, use tail
			with open(gpu_temp_file, 'rb') as f:
				f.seek(-2, os.SEEK_END)

				while f.read(1) != b'\n':
					f.seek(-2, os.SEEK_CUR)

				last_line = f.readline().decode('utf-8').strip()
				ms = rx_gput.search(last_line)

				if ms and ms.group(2).isnumeric() :
					log_time = datetime.datetime.strptime(ms.group(1), '%Y-%m-%d %H:%M:%S')
					if log_time > datetime.datetime.now() + gpu_log_time_delta :
						gput = int(ms.group(2))
						trace(f'GPU: {gput}')
				else:
					err(f'Failed to retrieve temp for gpu. Last line didn\'t match "{last_line}"')
		except Exception as e:
			err(f'Failed to retrieve temp for gpu', e)
			raise

	temp = max(cput, mobot, gput)
	set_fan_speed(temp, sys_temps, sys_fans)

def init_fans():
	all_fans = array.fans + ssds.fans + sys_fans

	for f in all_fans :
		shell(f'{fans_shell} set {f} 127')
		shell(f'{fans_shell} ctrl {f}')

def run():
	log('Setting Array fans')
	set_drive_fans(array)
	log('Setting SSD fans')
	set_drive_fans(ssds)
	log('Setting Sys fans')
	set_sys_fans()

init_fans()

while True :
	run()
	time.sleep(check_interval)
