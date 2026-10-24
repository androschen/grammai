"""Explicit local recovery; never remove sources or replace existing card IDs."""
import argparse,json,ctypes,msvcrt
from pathlib import Path
from ctypes import wintypes
from core.deck_recovery import recover_deck


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',required=True);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    try:
        result=recover_deck(dry_run=args.dry_run)
        if not args.dry_run and Path(result['target']).is_file():
            k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetFinalPathNameByHandleW.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
            with open(result['target'],'rb') as f:
                b=ctypes.create_unicode_buffer(32768);k.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(f.fileno()),b,len(b),0);result['physical_target']=b.value
        result['ok']=True
    except Exception as exc:result={'ok':False,'error':str(exc)}
    Path(args.report).write_text(json.dumps(result,indent=2),encoding='utf8')


if __name__=='__main__':main()
