"""Pinned components, resumable verified downloads and independent model records."""
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import hashlib,json,os,shutil,urllib.request,zipfile
from core.preferences import read_json,write_json


@dataclass(frozen=True)
class Asset:
    name:str
    url:str
    size:int
    sha:str


@dataclass(frozen=True)
class Component:
    id:str
    title:str
    kind:str
    version:str
    assets:tuple
    entry:str
    roles:tuple
    publisher:str
    license:str
    @property
    def size(self):return sum(a.size for a in self.assets)


def catalog():
    from core import speech_assets as s,local_assets as a
    revision='ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66'
    cpu_files=[('config.json',2309,'56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a'),('model.bin',145217532,'d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9'),('tokenizer.json',2203239,'fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab'),('vocabulary.txt',459861,'34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913')]
    values=[Component('speech-cpu','Whisper base · CPU','ct2',revision,tuple(Asset(n,f'https://huggingface.co/Systran/faster-whisper-base/resolve/{revision}/{n}',size,sha) for n,size,sha in cpu_files),'model.bin',('speech',),'Systran / OpenAI','MIT'),
        Component('speech-turbo','Whisper large-v3-turbo','ggml',s.MODEL_REVISION,(Asset(s.MODEL_NAME,s.MODEL_URL,s.MODEL_BYTES,s.MODEL_SHA),),s.MODEL_NAME,('speech',),'ggerganov / OpenAI','MIT'),
        Component('speech-runtime','Speech Vulkan runtime','runtime',s.VERSION,(Asset('runtime.zip',s.RUNTIME_URL,s.RUNTIME_BYTES,s.RUNTIME_SHA),),'whisper-server.exe',('speech',),'jiang1997/whisper.cpp-release · community build','MIT'),
        Component('qwen','Qwen3 4B','gguf',a.MODEL_REVISION,(Asset(a.MODEL_FILE,a.MODEL_URL,a.MODEL_BYTES,a.MODEL_SHA),),a.MODEL_FILE,('translation','learning'),'Qwen','Apache-2.0'),
        Component('ai-vulkan','AI Vulkan runtime','runtime',a.RUNTIME_VERSION,(Asset('runtime.zip',a.RUNTIME_URL,a.RUNTIME_BYTES,a.RUNTIME_SHA),),'llama-server.exe',('translation','learning'),'ggml-org/llama.cpp','MIT'),
        Component('ai-cpu','AI CPU runtime','runtime',a.RUNTIME_VERSION,(Asset('runtime.zip',f'https://github.com/ggml-org/llama.cpp/releases/download/{a.RUNTIME_VERSION}/llama-{a.RUNTIME_VERSION}-bin-win-cpu-x64.zip',19610948,'6b8d912796b6904771835d234f842e31e86d5e60da25555f9568d3bc88117bb9'),),'llama-server.exe',('translation','learning'),'ggml-org/llama.cpp','MIT')]
    values.extend([
        Component('speech-large','Whisper large-v3','ggml','5359861c739e955e79d9a303bcbc70fb988958b1',(Asset('ggml-large-v3-q5_0.bin','https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/ggml-large-v3-q5_0.bin',1081140203,'d75795ecff3f83b5faa89d1900604ad8c780abd5739fae406de19f23ecd98ad1'),),'ggml-large-v3-q5_0.bin',('speech',),'ggerganov / OpenAI','MIT'),
        Component('speech-qwen','Qwen3-ASR-1.7B · experimental','gguf','674df5d44b50a63e7102a18895ed20e3f91de301',(Asset('qwen3-asr-1.7b-q8_0.gguf','https://huggingface.co/cstr/qwen3-asr-1.7b-GGUF/resolve/674df5d44b50a63e7102a18895ed20e3f91de301/qwen3-asr-1.7b-q8_0.gguf',2506723200,'9851ab996591a2d0cb0efb216002764b509c86bd40c95e613d7b65b8e69c8a6e'),),'qwen3-asr-1.7b-q8_0.gguf',('speech',),'cstr conversion / Qwen','Apache-2.0'),
        Component('qwen-asr-runtime','Qwen ASR CPU / Vulkan runtime','runtime','v0.8.44',(Asset('runtime.zip','https://github.com/CrispStrobe/CrispASR/releases/download/v0.8.44/crispasr-windows-x86_64-vulkan.zip',36195865,'e674dab8c67eb37ddc859ff5ef1a634af44d40ef33f12b97ab610686f1b0427b'),),'crispasr.exe',('speech',),'CrispStrobe/CrispASR · community build','MIT')])
    from core.translation_assets import NLLB
    values.append(Component('translation-fast','NLLB fast translation','ct2',NLLB['revision'],tuple(Asset(**item) for item in NLLB['assets']),'model.bin',('translation',),'JustFrederik / Meta','CC-BY-NC-4.0'))
    return {c.id:c for c in values}


def digest(path,cancelled=lambda:False):
    value=hashlib.sha256()
    with Path(path).open('rb') as f:
        while block:=f.read(4*1024*1024):
            if cancelled():raise InterruptedError('Cancelled')
            value.update(block)
    return value.hexdigest()


def fetch(asset,path,progress=lambda m,p:None,cancelled=lambda:False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and path.stat().st_size==asset.size and digest(path,cancelled)==asset.sha:return
    part=path.with_suffix(path.suffix+'.part')
    offset=part.stat().st_size if part.exists() else 0
    if offset>asset.size:part.unlink();offset=0
    if offset==asset.size:
        if digest(part,cancelled)==asset.sha:part.replace(path);return
        part.unlink();offset=0
    headers={'User-Agent':'GrammAI-component-setup'}
    if offset:headers['Range']=f'bytes={offset}-'
    with urllib.request.urlopen(urllib.request.Request(asset.url,headers=headers),timeout=10) as response:
        resumed=offset and response.status==206
        if resumed and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise ValueError('Invalid resume response; retry the download.')
        if not resumed:offset=0
        with part.open('ab' if resumed else 'wb') as f:
            while block:=response.read(1024*1024):
                if cancelled():raise InterruptedError('Cancelled; download can be resumed.')
                offset+=len(block)
                if offset>asset.size:raise ValueError('Unexpected component size')
                f.write(block);progress(asset.name,min(99,int(100*offset/asset.size)))
            f.flush();os.fsync(f.fileno())
    if offset!=asset.size:raise ValueError('Download incomplete; retry to resume.')
    if digest(part,cancelled)!=asset.sha:
        part.unlink();raise ValueError('Checksum mismatch; file was not activated.')
    part.replace(path)


class ComponentManager:
    def __init__(self,root=None):
        from core.paths import model_root
        self.root=Path(root or model_root()).resolve()
    def records(self):
        from core.preferences import data_dir
        path=data_dir()/'components.json'
        if not path.exists():return {}
        try:
            value=json.loads(path.read_text(encoding='utf8'))
            if not isinstance(value,dict) or not isinstance(value.get('items'),dict):raise ValueError()
            return value['items']
        except (ValueError,OSError):raise ValueError('Component registry cannot be read; existing model files are safe.')
    def _save(self,records,root=None):
        write_json('components.json',{'schema':1,'root':str(root or self.root),'items':records})
    def path(self,identifier):
        record=self.records().get(identifier,{})
        if record.get('disconnected'):return None
        path=Path(record['path']) if record.get('path') else None
        if path and path.is_file():return path
        spec=catalog().get(identifier)
        if spec is None:return None
        base=self.root/'managed'/identifier/spec.version
        candidates=[base/spec.entry]
        if spec.kind=='runtime' and base.is_dir():
            entries=list(base.rglob(spec.entry))
            if len(entries)==1:candidates.append(entries[0])
        if identifier=='speech-cpu':
            caches=[Path.home()/'.cache/huggingface/hub']
            for name in ('HF_HUB_CACHE','HUGGINGFACE_HUB_CACHE'):
                if os.environ.get(name):caches.insert(0,Path(os.environ[name]))
            if os.environ.get('HF_HOME'):caches.insert(0,Path(os.environ['HF_HOME'])/'hub')
            candidates.extend(cache/'models--Systran--faster-whisper-base/snapshots'/spec.version/spec.entry for cache in caches)
        elif identifier=='translation-fast':
            candidates.append(Path.home()/'.grammai/models/nllb-200-distilled-600M-int8'/spec.entry)
        return next((p for p in candidates if p.is_file()),None)
    def availability(self,identifier):
        path=self.path(identifier)
        if path is None:return 'missing'
        spec=catalog()[identifier]
        try:
            if spec.kind!='runtime':
                if any(not (path.parent/a.name).is_file() or (path.parent/a.name).stat().st_size!=a.size for a in spec.assets):return 'incomplete'
            else:
                record=self.records().get(identifier,{})
                if path.stat().st_size==0:return 'incomplete'
                if record.get('managed'):
                    base=(self.root/'managed'/identifier/record['version']).resolve()
                    for name in record.get('hashes',{}):
                        file=(base/name).resolve()
                        if not file.is_relative_to(base) or not file.is_file():return 'incomplete'
        except OSError:return 'incomplete'
        return 'installed'

    def register(self,identifier,path,managed=False,hashes=None):
        path=Path(path).absolute()
        if not path.is_file():raise ValueError('Component file does not exist.')
        if managed and not path.resolve().is_relative_to((self.root/'managed').resolve()):raise ValueError('Managed component must be inside the managed folder.')
        records=self.records();records[identifier]=dict(path=str(path),managed=managed,hashes=hashes or {},version=catalog()[identifier].version)
        self._save(records);return path
    def adopt(self,config):
        from core.speech_assets import installed_paths
        from core.local_assets import managed_paths
        speech_exe,speech_model=installed_paths();ai_exe,ai_model=managed_paths()
        for identifier,path in [('speech-runtime',Path(config.vulkan_executable or speech_exe)),('speech-turbo',Path(config.vulkan_model or speech_model)),('ai-vulkan',Path(config.analysis_executable or ai_exe)),('qwen',Path(config.analysis_gguf or ai_model))]:
            expected=catalog()[identifier]
            # Custom files remain explicit paths; do not mislabel them as curated models.
            if path.is_file() and path.name==expected.entry and not self.path(identifier):self.register(identifier,path)
        try:
            from huggingface_hub import try_to_load_from_cache
            revision=catalog()['speech-cpu'].version
            cached=try_to_load_from_cache('Systran/faster-whisper-base','model.bin',revision=revision)
            if isinstance(cached,str) and not self.path('speech-cpu'):self.register('speech-cpu',cached)
        except (ImportError,OSError):pass
        cached=Path.home()/'.grammai/models/nllb-200-distilled-600M-int8/model.bin'
        if cached.is_file() and not self.path('translation-fast'):self.register('translation-fast',cached)
    def install(self,identifier,progress=lambda m,p:None,cancelled=lambda:False):
        spec=catalog()[identifier]
        existing=self.path(identifier)
        if existing and spec.kind=='runtime' and not self.records().get(identifier,{}).get('managed'):
            if not self.records().get(identifier):self.register(identifier,existing)
            if self.availability(identifier)!='installed':raise ValueError('Runtime files are incomplete. Repair or import a complete runtime.')
            return existing
        if existing:
            if spec.kind=='ct2':
                for asset in spec.assets:
                    file=existing.parent/asset.name
                    if file.is_file():
                        if file.stat().st_size!=asset.size or digest(file,cancelled)!=asset.sha:raise ValueError('Existing model files differ from the curated version; keep the custom model or import matching files.')
                    else:fetch(asset,file,progress,cancelled)
            if not self.records().get(identifier):self.register(identifier,existing)
            self.verify(identifier,progress,cancelled);return existing
        self.root.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(self.root).free<spec.size*2+100*1024**2:raise ValueError('Not enough free space for download and staging.')
        target=self.root/'managed'/identifier/spec.version
        if target.exists():
            raise ValueError('An unregistered component folder exists. Import or inspect it before replacing it.')
        stage=target.with_name(target.name+'.staging-'+uuid4().hex);stage.mkdir(parents=True)
        hashes={}
        try:
            for asset in spec.assets:
                if cancelled():raise InterruptedError('Cancelled')
                cached=self.root/'downloads'/identifier/asset.name
                fetch(asset,cached,progress,cancelled)
                if asset.name.endswith('.zip'):
                    with zipfile.ZipFile(cached) as archive:
                        for member in archive.infolist():
                            candidate=(stage/member.filename).resolve()
                            if not candidate.is_relative_to(stage.resolve()) or ((member.external_attr>>16)&0o170000)==0o120000:raise ValueError('Unsafe archive member')
                            if cancelled():raise InterruptedError('Cancelled')
                            archive.extract(member,stage)
                else:shutil.copy2(cached,stage/asset.name)
            for path in stage.rglob('*'):
                if path.is_file():hashes[str(path.relative_to(stage))]=digest(path,cancelled)
            entries=list(stage.rglob(spec.entry))
            if len(entries)!=1:raise ValueError('Component entry point missing or ambiguous.')
            relative=entries[0].relative_to(stage);stage.replace(target)
            try:self.register(identifier,target/relative,True,hashes)
            except Exception:
                target.rename(stage);raise
            for asset in spec.assets:(self.root/'downloads'/identifier/asset.name).unlink(missing_ok=True)
            progress(spec.title,100);return target/relative
        finally:
            if stage.exists() and stage.resolve().is_relative_to((self.root/'managed').resolve()):shutil.rmtree(stage)
    def verify(self,identifier,progress=lambda m,p:None,cancelled=lambda:False):
        spec=catalog()[identifier];record=self.records().get(identifier);path=self.path(identifier)
        if not path or not record:raise ValueError('Component is not installed.')
        if record.get('hashes'):
            base=self.root/'managed'/identifier/record['version']
            for name,expected in record['hashes'].items():
                file=(base/name).resolve()
                if not file.is_relative_to(base.resolve()) or not file.is_file() or digest(file,cancelled)!=expected:raise ValueError('Component verification failed: '+name)
        elif spec.kind!='runtime':
            for asset in spec.assets:
                file=path.parent/asset.name
                if not file.is_file() or file.stat().st_size!=asset.size or digest(file,cancelled)!=asset.sha:raise ValueError('External model differs from the curated version. Keep the external path or import the matching model.')
        else:raise ValueError('External runtime has no managed integrity record. Reinstall a managed runtime to verify its complete files.')
        progress('Verified '+spec.title,100);return True
    def repair(self,identifier,progress=lambda m,p:None,cancelled=lambda:False):
        records=self.records();old=records.pop(identifier,None);backup=None;target=None
        if old and old.get('managed'):
            target=(self.root/'managed'/identifier/old['version']).resolve()
            if not target.is_relative_to((self.root/'managed').resolve()):raise ValueError('Unsafe repair path')
            if target.exists():backup=target.with_name(target.name+'.repair-'+uuid4().hex);target.rename(backup)
        self._save(records)
        try:result=self.install(identifier,progress,cancelled)
        except Exception:
            records=self.records()
            if old:records[identifier]=old
            self._save(records)
            if backup and backup.exists():backup.rename(target)
            raise
        if backup and backup.exists() and backup.resolve().is_relative_to((self.root/'managed').resolve()):shutil.rmtree(backup)
        return result
    def disconnect(self,identifier):
        record=self.records().get(identifier,{})
        if record.get('managed'):raise ValueError('Use Delete for managed files.')
        records=self.records();records[identifier]={'disconnected':True}
        self._save(records)
    def remove(self,identifier):
        record=self.records().get(identifier)
        if not record or not record.get('managed'):raise ValueError('External files are never removed by GrammAI.')
        target=(self.root/'managed'/identifier/record['version']).resolve()
        if not target.is_relative_to((self.root/'managed').resolve()) or target==self.root.resolve():raise ValueError('Unsafe component path')
        if target.exists():shutil.rmtree(target)
        records=self.records();records.pop(identifier);self._save(records)
    def move(self,destination,progress=lambda m,p:None,cancelled=lambda:False):
        destination=Path(destination).resolve();old_root=self.root
        if destination==old_root:return
        if destination.is_relative_to(old_root) or old_root.is_relative_to(destination):raise ValueError('Choose a separate folder outside the current model folder.')
        records=self.records();managed={k:v for k,v in records.items() if v.get('managed')}
        required=sum(p.stat().st_size for p in (old_root/'managed').rglob('*') if p.is_file())
        destination.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(destination).free<required+100*1024**2:raise ValueError('Not enough free space to move models.')
        updates={};sources=[]
        for identifier,record in managed.items():
            source=(old_root/'managed'/identifier/record['version']).resolve()
            if not source.is_relative_to((old_root/'managed').resolve()):raise ValueError('Unsafe source folder')
            self.verify(identifier,progress,cancelled)
            target=destination/'managed'/identifier/record['version']
            target.parent.mkdir(parents=True,exist_ok=True)
            stage=target.with_name(target.name+'.moving-'+uuid4().hex)
            try:
                if not target.exists():shutil.copytree(source,stage)
                checking=target if target.exists() else stage
                for name,expected in record['hashes'].items():
                    if digest(checking/name,cancelled)!=expected:raise ValueError('Copied component verification failed.')
                if stage.exists():stage.replace(target)
            finally:
                if stage.exists() and stage.resolve().is_relative_to((destination/'managed').resolve()):shutil.rmtree(stage)
            updates[identifier]=dict(record,path=str(target/Path(record['path']).relative_to(source)));sources.append(source)
        records.update(updates);self._save(records,destination)
        self.root=destination
        for source in sources:
            if source.is_relative_to((old_root/'managed').resolve()):shutil.rmtree(source)
        progress('Managed models moved; external files stay in place.',100)


def resolve(identifier):
    return ComponentManager().path(identifier)
