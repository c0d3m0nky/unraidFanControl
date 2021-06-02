from dataclasses import dataclass
from collections.abc import Callable
from typing import List, Any, Dict, Tuple

import os
import subprocess
import time
import datetime
import re
import sys

# region Infra

check_interval = 60
trace_log = True
fanset_log = True
dry_run = False
gpu_temp_file = './gputemp.log'
fans_shell = '/mnt/user/projects/fanControl/fans.sh'


def shell(cmd, check=False) -> str:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True, check=check)
    return res.stdout.decode('utf-8').strip()


def logts() -> str:
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log_fanset(msg) -> None:
    if fanset_log:
        print(f'{logts()}\tFANSET\n<-------------\n{msg}\n------------->')


def trace(msg) -> None:
    if trace_log:
        print(f'{logts()}\tTRACE\t{msg}')


def log(msg) -> None:
    print(f'{logts()}\tLOG\t{msg}')


def err(msg, e=None) -> None:
    if e:
        print(f'{logts()}\tERROR\t{msg}\n\n{e}\n\n')
    else:
        print(f'{logts()}\tERROR\t{msg}')


# endregion

# region Classes


@dataclass
class Temp:
    temp: int
    pwm: int


@dataclass
class Sensor:
    name: str
    id: str
    get_temp: Callable[[Any], int]
    offset: int


@dataclass
class Sensors:
    name: str
    sensors: List[Sensor]
    fans: List[str]
    temps: List[Temp]


@dataclass
class SensorsFanSet:
    src: str
    fans: List[str]
    pwm: int
    temp: int
    temp_actual: int


# endregion

def get_drive_temp(sensor: Sensor) -> int:
    sleeping = shell(f'hdparm -C {sensor.id} | grep -c standby')
    log_name = f'{sensor.name} ({sensor.id})'
    if sleeping == "0":
        temp = shell(
            f"smartctl -d ata -A {sensor.id} | grep -m 1 -Ei '(Temperature_Celsius|Airflow_Temperature_Cel)' | awk '{{print $10}}'")

        if temp.isnumeric():
            temp = int(temp)
        else:
            err(f'Failed to retrieve temp for {log_name}')
            return -1

        temp_log = temp

        if sensor.offset != 0:
            temp_log = f'{temp+sensor.offset}[{temp}]'

        trace(f'{log_name} at {temp_log} celcius')
        return int(temp)

    trace(f'{log_name} is asleep')
    return 0


rx_mobot = re.compile("MB Temp: +.(\d{2,})\.")
rx_cput = re.compile("CPU Temp: +.(\d{2,})\.")


def get_sys_temp(sensor: Sensor) -> int:
    temps = shell('sensors | grep -E "(MB|CPU) Temp:"')
    temp = 0
    rx = None

    if sensor.id == 'CPU':
        rx = rx_cput
    elif sensor.id == 'MB':
        rx = rx_mobot
    else:
        err(f'Invalid sys sensor id {sensor.id}')
        return -1
    
    ms = rx.search(temps)

    if ms and ms.group(1).isnumeric() :
        temp = int(ms.group(1))
        trace(f'{sensor.name} at {temp}')
    else:
        err(f'Failed to retrieve temp {sensor.name}')
        return -1
    
    return temp


curr_gpu_temp: int = 0
curr_fan_pwms: Dict[str, Tuple[int, bool]] = None

config: List[Sensors] = [
    Sensors(
        'Array',
        [
            Sensor('A3-WD500gb', '/dev/sdf', get_drive_temp, 0),
            Sensor('A1-WD3tb', '/dev/sdc', get_drive_temp, 0),
            Sensor('A2-SG4tb', '/dev/sdg', get_drive_temp, -4),
            Sensor('A4-IW4tB', '/dev/sde', get_drive_temp, 0),
        ],
        ['CHA1', 'CHA2'],
        [
            Temp(32, 75), Temp(35, 127), Temp(40, 175),
            Temp(45, 225), Temp(50, 254)
        ]
    ),
    Sensors(
        'SSDs',
        [
            Sensor('Cache', '/dev/sdb', get_drive_temp, -1),
            Sensor('DB-SSD', '/dev/sdd', get_drive_temp, -1)
        ],
        ['CPU2'],
        [Temp(32, 127), Temp(35, 165), Temp(40, 225), Temp(45, 254)]
    ),
    Sensors(
        'GPU',
        [Sensor('GPU', 'GPU', lambda s: curr_gpu_temp, 0)],
        ['CHA3'],
        [Temp(40, 127), Temp(50, 165), Temp(60, 180), Temp(70, 225), Temp(75, 254)]
    ),
    Sensors(
        'CPU/MB',
        [
            Sensor('CPU', 'CPU', get_sys_temp, 0),
            Sensor('MB', 'MB', get_sys_temp, 0)
        ],
        ['CHA3'],
        [Temp(40, 127), Temp(50, 150), Temp(60, 180), Temp(70, 225), Temp(75, 254)]
    )
]


def get_fanset(sensors: Sensors) -> SensorsFanSet:
    max_temp = 0
    max_temp_actual = 0
    trigger_sensor = ''

    # do this with iter tools
    for s in sensors.sensors:
        temp_actual = s.get_temp(s) 
        temp = temp_actual + s.offset

        if temp > max_temp:
            max_temp = temp
            max_temp_actual = temp_actual
            trigger_sensor = s.name

    last_pwm = 0

    for t in sensors.temps:
        if max_temp < t.temp:
            break
        last_pwm = t.pwm

    return SensorsFanSet(trigger_sensor, sensors.fans, last_pwm, max_temp, max_temp_actual)


def commit_fanpwm(fan: str, pwm: int, src: str):
    (cpwm, cenb) = curr_fan_pwms[fan]

    if not dry_run and not cenb:
        log_fanset(f'{fan} control not enabled')
        return
    elif pwm == cpwm:
        return
    elif pwm > 0:
        log_fanset(f'Set {fan} to {pwm} ({src})')
    else:
        log_fanset(f'Shut off {fan}')

    if not dry_run:
        shell(f'{fans_shell} set {fan} {pwm}')


def commit_fansets(sets: List[SensorsFanSet]):
    fans: Dict[str, Tuple[int, str]] = dict()

    for s in sets:
        for f in s.fans:
            if f in fans.keys() and fans[f][0] > s.pwm:
                continue

            src = f'{s.src} {s.temp}'

            if s.temp != s.temp_actual:
                src += f'[{s.temp_actual}]'

            fans[f] = (s.pwm, src)

    for i, (fan, (pwm, src)) in enumerate(fans.items()):
        commit_fanpwm(fan, pwm, src)


def init_fans():
    trace('Initializing fans')
    all_fans: Dict[str, bool] = dict()

    for s in config:
        for f in s.fans:
            if not f in all_fans.keys():
                all_fans[f] = True

    for f in all_fans.keys():
        if dry_run:
            log(f'fans_shell ctrl {f}')
            log(f'fans_shell set {f} 127')
        else:
            shell(f'{fans_shell} ctrl {f}')
            shell(f'{fans_shell} set {f} 127')


def init_check():
    chk = shell(f"{fans_shell} ls | head -n 1 | awk '{{ print $3 }}'")

    if chk != '1':
        err('Fans were not initialized, doing so now')
        init_fans()

def set_current_pwms() -> bool:
    global curr_fan_pwms

    curr_fan_pwms = None
    curr = shell(f"{fans_shell} ls | awk '{{ print $2, $3, $4 }}'")

    if not curr == '':
        curr_fan_pwms = dict()
        for f in list(map(lambda c: c.split(), curr.split('\n'))):
            curr_fan_pwms[f[0]] = (int(f[2]), f[1] == "1")
        return True

    return False


def run():
    trace('Starting check')
    if not set_current_pwms():
        err('Failed to retrieve current fan settings')
        return

    fansets: List[SensorsFanSet] = list()

    trace('Starting set')
    for s in config:
        fanset = get_fanset(s)
        fansets.append(fanset)

    commit_fansets(fansets)
    if trace_log:
        log_fanset(shell(f'{fans_shell} ls'))
    trace('Run complete')


if len(sys.argv) > 1:
    if sys.argv[1] == 'init':
        init_fans()
    elif sys.argv[1] == 'loop':
        init_fans()
        while True:
            run()
            time.sleep(check_interval)
else:
    log('Starting fanControl')
    init_check()
    run()
