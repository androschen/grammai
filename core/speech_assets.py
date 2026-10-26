"""Pinned speech assets; community Vulkan binary is explicitly identified."""
from pathlib import Path
import zipfile
from core.local_assets import download

from core.paths import model_root,model_candidates
ROOT=model_root()/'speech'
VERSION='1.8.4-community-vulkan'
RUNTIME_URL='https://github.com/jiang1997/whisper.cpp-release/releases/download/v1.8.4.1/whisper-1.8.4-windows-x64.zip'
RUNTIME_BYTES=37802904
RUNTIME_SHA='4b1b36343feb55ec3deace6a7dd18cc217f43a55e4ecce76ccd4ee3595c0b642'
UPSTREAM_COMMIT='3e9b7d0fef3528ee2208da3cdb873a2c53d2ae2f'
MODEL_REVISION='5359861c739e955e79d9a303bcbc70fb988958b1'
MODEL_NAME='ggml-large-v3-turbo-q5_0.bin'
MODEL_URL=f'https://huggingface.co/ggerganov/whisper.cpp/resolve/{MODEL_REVISION}/{MODEL_NAME}'
MODEL_BYTES=574041195
MODEL_SHA='394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2'


def installed_paths():
    for root in model_candidates('speech'):
        servers=list((root/VERSION).rglob('whisper-server.exe'))
        if servers and (root/MODEL_NAME).is_file():
            return servers[0],root/MODEL_NAME
    root=model_root()/'speech'
    return root/VERSION/'whisper-server.exe',root/MODEL_NAME


def install(progress=lambda message,percent:None,cancelled=lambda:False):
    ROOT.mkdir(parents=True,exist_ok=True)
    archive=ROOT/'whisper-vulkan.zip'
    download(RUNTIME_URL,archive,RUNTIME_BYTES,RUNTIME_SHA,progress,cancelled)
    destination=ROOT/VERSION
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            if not (destination/member.filename).resolve().is_relative_to(destination.resolve()):
                raise ValueError('Unsafe archive path')
            if cancelled():
                raise InterruptedError('Cancelled')
            package.extract(member,destination)
    download(MODEL_URL,ROOT/MODEL_NAME,MODEL_BYTES,MODEL_SHA,progress,cancelled)
    executable,model=installed_paths()
    if not executable.is_file():
        raise RuntimeError('Speech runtime has no whisper-server.exe')
    return {'executable':str(executable.resolve()),'model':str(model.resolve()),
        'publisher':'jiang1997/whisper.cpp-release (community build)','upstream_commit':UPSTREAM_COMMIT}


if __name__=='__main__':
    last=[None]
    def report(message,percent):
        value=(message,percent//10)
        if value!=last[0]:
            print(f'{message}: {percent}%',flush=True)
            last[0]=value
    print(install(report),flush=True)
