from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata
from importlib.util import find_spec

root=Path(SPECPATH).parent
datas=[(str(root/'ui'/'assets'),'ui/assets')]
datas.append((str(root/'packaging'/'THIRD_PARTY_NOTICES.txt'),'.'))
for package in ('faster_whisper','pypinyin','pythainlp','transformers','certifi'):
    datas+=collect_data_files(package)
for package in ('transformers','huggingface_hub','tokenizers','ctranslate2','faster_whisper','sentencepiece','numpy','regex','safetensors','tqdm','packaging','requests','filelock','pyyaml','PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','soundcard','pythainlp','pypinyin','av','psutil','onnxruntime'):
    datas+=copy_metadata(package)
binaries=[]
for package in ('ctranslate2','onnxruntime'):
    binaries+=collect_dynamic_libs(package)
hidden=['_cffi_backend','transformers.models.nllb.tokenization_nllb',
        'transformers.models.m2m_100.tokenization_m2m_100',
        'transformers.models.m2m_100.configuration_m2m_100',
        'transformers.models.auto.tokenization_auto','sentencepiece',
        'pythainlp.transliterate.royin','pythainlp.tokenize.newmm']
# AutoTokenizer otherwise pulls in hundreds of unrelated model architectures.
models=Path(next(iter(find_spec('transformers').submodule_search_locations)))/'models'
unused_models=['transformers.models.'+p.name for p in models.iterdir()
    if p.is_dir() and p.name not in ('auto','nllb','m2m_100','encoder_decoder','__pycache__')]
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=binaries,datas=datas,
    runtime_hooks=[str(root/'packaging'/'runtime_hook.py')],
    hiddenimports=hidden,excludes=unused_models+['torch','tensorflow','jax','matplotlib','IPython','pytest','tkinter','PyQt5','PyQt6','pythainlp.phayathaibert'])
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='GrammAI',debug=False,
    strip=False,upx=False,console=False,icon=str(root/'ui'/'assets'/'grammai.ico'),
    version=str(root/'packaging'/'version.txt'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='GrammAI')
