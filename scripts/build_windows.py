"""Build a portable exe folder and optionally an Inno Setup installer."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer',action='store_true')
    parser.add_argument('--register-models',action='store_true',help='Record existing development models in this user profile, never in the bundle')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    app=QApplication.instance() or QApplication([])
    icon=root/'ui/assets/grammai.ico'
    source_icon=root/'ui/assets/grammai.svg'
    if not icon.is_file() or source_icon.stat().st_mtime>icon.stat().st_mtime:
        if not QIcon(str(source_icon)).pixmap(256,256).save(str(icon)):
            raise RuntimeError('Could not generate the Windows icon')
    if args.register_models:
        from core.paths import register_existing_models
        register_existing_models()
    env=dict(os.environ)
    # Optional NLP modules may otherwise attempt downloads during hook discovery.
    env['HF_HUB_OFFLINE']='1'
    env['PYTHAINLP_OFFLINE']='1'
    env['HF_HUB_DISABLE_SYMLINKS_WARNING']='1'
    tools=root/'.build-tools/python'
    if tools.is_dir():
        env['PYTHONPATH']=str(tools)+os.pathsep+env.get('PYTHONPATH','')
    (root/'build').mkdir(exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='windows-stage-',dir=root/'build'))
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(stage),
        '--workpath',str(root/'build'),'--log-level','WARN',str(root/'packaging/grammai.spec')],cwd=root,env=env,check=True)
    if args.installer:
        compiler=root/'.build-tools/inno/ISCC.exe'
        if not compiler.is_file():
            located=shutil.which('ISCC')
            compiler=Path(located) if located else Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Inno Setup 6/ISCC.exe'
        if not compiler.is_file():
            raise RuntimeError('Install Inno Setup 6 or add ISCC.exe to PATH; the portable build is ready in dist/GrammAI')
        subprocess.run([str(compiler),'/Q','/DAppSource='+str(stage/'GrammAI'),str(root/'packaging/installer.iss')],cwd=root,check=True)
    from core.version import APP_VERSION
    (root/'dist').mkdir(exist_ok=True)
    shutil.make_archive(str(root/'dist'/f'GrammAI-Portable-{APP_VERSION}'),'zip',root_dir=stage,base_dir='GrammAI')
    (root/'build'/'latest-bundle.txt').write_text(str(stage/'GrammAI'),encoding='utf8')
    print('Windows build ready in '+str(root/'dist'))


if __name__=='__main__':
    main()
