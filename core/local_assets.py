"""Pinned, checksummed local AI assets. Downloads never include conversation data."""
import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

from core.paths import model_root,model_candidates
ASSET_ROOT = model_root() / 'local-ai'
RUNTIME_VERSION = 'b11707'
RUNTIME_FILE = 'llama-b11707-bin-win-vulkan-x64.zip'
RUNTIME_URL = f'https://github.com/ggml-org/llama.cpp/releases/download/{RUNTIME_VERSION}/{RUNTIME_FILE}'
RUNTIME_SHA = '9c7d17c12053bf95b03a179f9bcdf15fdeafe680a4f2845d23bc951bc18c0fa5'
RUNTIME_BYTES = 32260710
MODEL_FILE = 'Qwen3-4B-Q4_K_M.gguf'
MODEL_REVISION = 'bc640142c66e1fdd12af0bd68f40445458f3869b'
MODEL_URL = f'https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/{MODEL_REVISION}/{MODEL_FILE}'
MODEL_SHA = '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'
MODEL_BYTES = 2497280256


def managed_paths(root=None):
    if root is None:
        for candidate in model_candidates('local-ai'):
            if (candidate/RUNTIME_VERSION/'llama-server.exe').is_file() and (candidate/MODEL_FILE).is_file():
                return candidate/RUNTIME_VERSION/'llama-server.exe',candidate/MODEL_FILE
        root=model_root()/'local-ai'
    root = Path(root)
    return root / RUNTIME_VERSION / 'llama-server.exe', root / MODEL_FILE


def sha256(path, cancelled=lambda: False):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            if cancelled():
                raise InterruptedError('Cancelled')
            digest.update(block)
    return digest.hexdigest()


def download(url, path, expected_bytes, expected_sha, progress, cancelled):
    path = Path(path)
    if path.is_file() and path.stat().st_size == expected_bytes:
        progress('Checking existing ' + path.name, 0)
        if sha256(path, cancelled) == expected_sha:
            return
    partial = path.with_suffix(path.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'GrammAI-local-setup'})
    digest, count = hashlib.sha256(), 0
    # Downloads are explicit setup operations; analysis itself has no external requests.
    with urllib.request.urlopen(request, timeout=30) as response, partial.open('wb') as stream:
        while block := response.read(1024 * 1024):
            if cancelled():
                raise InterruptedError('Download cancelled. Restart setup to download again.')
            count += len(block)
            if count > expected_bytes:
                raise ValueError('Unexpected download size; installation stopped.')
            stream.write(block)
            digest.update(block)
            progress(path.name, min(100, int(count * 100 / expected_bytes)))
    if count != expected_bytes or digest.hexdigest() != expected_sha:
        raise ValueError('Checksum/size mismatch. File was not installed; retry setup.')
    partial.replace(path)


def install(progress=lambda message, percent: None, cancelled=lambda: False, root=None):
    root = Path(root or model_root()/'local-ai')
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < MODEL_BYTES + 512 * 1024 ** 2:
        raise ValueError('At least 3 GB of free disk space is required for setup.')
    archive = root / RUNTIME_FILE
    download(RUNTIME_URL, archive, RUNTIME_BYTES, RUNTIME_SHA, progress, cancelled)
    runtime = root / RUNTIME_VERSION
    runtime.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            destination = (runtime / member.filename).resolve()
            if not destination.is_relative_to(runtime.resolve()):
                raise ValueError('Unsafe runtime archive path.')
            if cancelled():
                raise InterruptedError('Cancelled')
            package.extract(member, runtime)
    executable = next(runtime.rglob('llama-server.exe'), None)
    if executable is None:
        raise ValueError('Runtime archive contains no llama-server.exe.')
    model = root / MODEL_FILE
    download(MODEL_URL, model, MODEL_BYTES, MODEL_SHA, progress, cancelled)
    progress('Local model and Vulkan runtime installed', 100)
    return {'executable': str(executable.resolve()), 'model': str(model.resolve())}


if __name__ == '__main__':
    last = [None]
    def report(message, percent):
        state = (message, percent // 10)
        if state != last[0]:
            print(f'{message}: {percent}%', flush=True)
            last[0] = state
    print(install(report))
