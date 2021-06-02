
import re


temps = 'MB Temp:      +38.8°C\nCPU Temp:     +38.8°C'
rx = re.compile("CPU Temp: +.(\d{2,})\.")
ms = rx.search(temps)

print(ms.group(1))