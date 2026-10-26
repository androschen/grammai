"""Bounded, cancellable retries for pinned model downloads; never bypass TLS checks."""
import hashlib
import http.client
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ATTEMPTS=5
TIMEOUT=30


def checksum(path,cancelled):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(4*1024*1024):
            if cancelled():raise InterruptedError('Cancelled; download can be resumed.')
            value.update(block)
    return value.hexdigest()


def retryable(error):
    if isinstance(error,urllib.error.HTTPError):return error.code in (408,429,500,502,503,504)
    reason=error.reason if isinstance(error,urllib.error.URLError) else error
    if isinstance(reason,(ssl.SSLError,ssl.CertificateError)):return False
    return isinstance(error,(urllib.error.URLError,ConnectionError,TimeoutError,http.client.IncompleteRead))


def wait_to_retry(seconds,cancelled):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if cancelled():raise InterruptedError('Cancelled; download can be resumed.')
        time.sleep(min(.1,max(0,deadline-time.monotonic())))


def download_verified(asset,path,progress=lambda m,p:None,cancelled=lambda:False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    part=path.with_suffix(path.suffix+'.part')
    host=urlsplit(asset.url).hostname or 'download host'
    if path.is_file() and path.stat().st_size==asset.size and checksum(path,cancelled)==asset.sha:return
    for attempt in range(ATTEMPTS):
        if cancelled():raise InterruptedError('Cancelled; download can be resumed.')
        offset=part.stat().st_size if part.exists() else 0
        if offset>asset.size:part.unlink();offset=0
        if offset==asset.size:
            if checksum(part,cancelled)==asset.sha:part.replace(path);return
            part.unlink();offset=0
        headers={'User-Agent':'GrammAI-component-setup','Accept-Encoding':'identity'}
        if offset:headers['Range']=f'bytes={offset}-'
        try:
            progress(('Resuming ' if offset else 'Downloading ')+asset.name+' from '+host,min(99,int(offset*100/asset.size)))
            with urllib.request.urlopen(urllib.request.Request(asset.url,headers=headers),timeout=TIMEOUT) as response:
                resumed=bool(offset and getattr(response,'status',200)==206)
                response_headers=getattr(response,'headers',{})
                if getattr(response,'status',200)==206:
                    match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response_headers.get('Content-Range',''))
                    if not match or int(match[1])!=offset or int(match[2])<offset or int(match[2])>=asset.size or int(match[3])!=asset.size:
                        raise ValueError('Invalid resume response for '+asset.name+'. Saved partial file was kept; retry the download.')
                if not resumed:offset=0
                with part.open('ab' if resumed else 'wb') as stream:
                    def write(block):
                        nonlocal offset
                        if offset+len(block)>asset.size:raise ValueError('Unexpected download size for '+asset.name+'. File was not activated.')
                        stream.write(block);offset+=len(block)
                        progress(asset.name,min(99,int(offset*100/asset.size)))
                    while True:
                        if cancelled():raise InterruptedError('Cancelled; download can be resumed.')
                        try:block=response.read(1024*1024)
                        except http.client.IncompleteRead as exc:
                            if exc.partial:write(exc.partial)
                            raise
                        if not block:break
                        write(block)
                    stream.flush();os.fsync(stream.fileno())
            if offset!=asset.size:raise ConnectionError('Download ended before the complete file arrived')
        except (urllib.error.URLError,ConnectionError,TimeoutError,http.client.IncompleteRead,ssl.SSLError) as exc:
            if isinstance(exc,urllib.error.HTTPError):exc.close()
            # A read may have delivered its final bytes before reporting a reset.
            if part.is_file() and part.stat().st_size==asset.size and checksum(part,cancelled)==asset.sha:
                part.replace(path);return
            if not retryable(exc) or attempt==ATTEMPTS-1:
                detail=('HTTP '+str(exc.code)) if isinstance(exc,urllib.error.HTTPError) else 'TLS verification failed' if isinstance(getattr(exc,'reason',exc),(ssl.SSLError,ssl.CertificateError)) else 'connection interrupted'
                raise OSError('Could not download '+asset.name+' from '+host+' ('+detail+'). Saved progress is kept. Retry to resume; if it repeats, check access to '+host+' or try another network.') from exc
            delay=min(2**attempt,8)
            if isinstance(exc,urllib.error.HTTPError):
                try:delay=max(delay,min(30,int(exc.headers.get('Retry-After',0))))
                except (ValueError,TypeError,AttributeError):pass
            progress('Connection interrupted · '+asset.name+' · retry '+str(attempt+1)+'/'+str(ATTEMPTS-1)+' in '+str(delay)+'s',min(99,int((part.stat().st_size if part.exists() else 0)*100/asset.size)))
            wait_to_retry(delay,cancelled);continue
        if checksum(part,cancelled)!=asset.sha:
            part.unlink();raise ValueError('Checksum mismatch for '+asset.name+'. File was not activated; retry the download.')
        part.replace(path);return
