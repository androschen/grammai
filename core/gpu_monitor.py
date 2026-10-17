"""Optional Windows PDH process GPU counters; no shell polling or extra package."""
import ctypes
import os
import re
from ctypes import wintypes


class CounterValue(ctypes.Structure):
    _fields_=[('status',wintypes.DWORD),('value',ctypes.c_double)]


class CounterItem(ctypes.Structure):
    _fields_=[('name',wintypes.LPWSTR),('value',CounterValue)]


class WindowsGpuMonitor:
    def __init__(self):
        self.query=ctypes.c_void_p()
        self.counters=[]
        self.available=False
        if os.name!='nt':
            return
        try:
            self.pdh=ctypes.WinDLL('pdh')
            self.pdh.PdhOpenQueryW.argtypes=[wintypes.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(ctypes.c_void_p)]
            self.pdh.PdhAddEnglishCounterW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(ctypes.c_void_p)]
            self.pdh.PdhCollectQueryData.argtypes=[ctypes.c_void_p]
            self.pdh.PdhGetFormattedCounterArrayW.argtypes=[ctypes.c_void_p,wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
            self.pdh.PdhCloseQuery.argtypes=[ctypes.c_void_p]
            if self.pdh.PdhOpenQueryW(None,0,ctypes.byref(self.query)):
                return
            for path in (r'\GPU Engine(*)\Utilization Percentage',r'\GPU Process Memory(*)\Dedicated Usage'):
                counter=ctypes.c_void_p()
                if self.pdh.PdhAddEnglishCounterW(self.query,path,0,ctypes.byref(counter)):
                    self.close()
                    return
                self.counters.append(counter)
            self.pdh.PdhCollectQueryData(self.query)
            self.available=True
        except (AttributeError,OSError):
            self.close()

    def _values(self,counter):
        size,count=wintypes.DWORD(),wintypes.DWORD()
        self.pdh.PdhGetFormattedCounterArrayW(counter,0x200,ctypes.byref(size),ctypes.byref(count),None)
        if not size.value or size.value>16*1024*1024:
            return []
        buffer=ctypes.create_string_buffer(size.value)
        if self.pdh.PdhGetFormattedCounterArrayW(counter,0x200,ctypes.byref(size),ctypes.byref(count),buffer):
            return []
        values=ctypes.cast(buffer,ctypes.POINTER(CounterItem))
        return [(values[i].name,values[i].value.value) for i in range(count.value)
                if values[i].value.status in (0,1)]

    @staticmethod
    def aggregate(engines,memory,pids):
        def owned(name):
            match=re.search(r'pid_(\d+)_',name)
            return bool(match and int(match[1]) in pids)
        # Report the busiest app engine, not a misleading sum of different engines.
        gpu=max([value for name,value in engines if owned(name)]+[0])
        used=sum(value for name,value in memory if owned(name))
        return {'gpu_percent':max(0,min(100,gpu)),'gpu_memory_mb':used/1024**2}

    def sample(self,pids):
        unavailable={'gpu_percent':None,'gpu_memory_mb':None}
        if not self.available or self.pdh.PdhCollectQueryData(self.query):
            return unavailable
        engines,memory=(self._values(counter) for counter in self.counters)
        if not engines and not memory:
            return unavailable
        return self.aggregate(engines,memory,set(pids))

    def close(self):
        if self.query.value:
            self.pdh.PdhCloseQuery(self.query)
            self.query=ctypes.c_void_p()
        self.counters=[]
        self.available=False
