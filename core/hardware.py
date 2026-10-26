"""Hardware capability probes; a GPU name alone never proves acceleration works."""
import os,platform,re,subprocess
from functools import lru_cache
import psutil


def default_threads():
    return max(1,min(8,(psutil.cpu_count(logical=False) or os.cpu_count() or 2)//2))


def system_info():
    return dict(cpu=platform.processor() or 'CPU',architecture=platform.machine(),ram_bytes=psutil.virtual_memory().total,threads=default_threads(),display_adapters=display_adapters())


def vulkan_devices(output):
    return [{'id':m[1],'name':m[2].strip()} for m in re.finditer(r'^\s*(Vulkan\d+):\s*([^\r\n]+)',output,re.M)]


def probe_devices(executable):
    result=subprocess.run([str(executable),'--list-devices'],capture_output=True,text=True,errors='replace',timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:return []
    return vulkan_devices(result.stdout+'\n'+result.stderr)


def select_device(devices,preferred=''):
    if preferred:return next((d for d in devices if d['id']==preferred),None)
    return next(iter(devices),None)


@lru_cache(maxsize=1)
def display_adapters():
    if platform.system()!='Windows':return []
    try:
        import json
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name)"],
            capture_output=True,text=True,encoding='utf-8-sig',errors='replace',timeout=12,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:return []
        names=json.loads(result.stdout)
        if isinstance(names,str):names=[names]
        return [n for n in names if isinstance(n,str) and any(v in n.lower() for v in ('nvidia','radeon','amd','intel'))]
    except (OSError,ValueError,subprocess.TimeoutExpired):return []
