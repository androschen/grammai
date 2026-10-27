"""Feature-based first-run planning; discovery never hashes or loads models."""
from dataclasses import dataclass
from pathlib import Path
from core.components import catalog
from core.setup import required_components,select_configuration

@dataclass(frozen=True)
class SetupPlan:
    speech:str
    processing:str
    learning:bool
    translation:bool
    backup:bool=False
    @property
    def identifiers(self):return required_components(self.speech,self.processing,self.learning,self.translation,self.backup)
    def configuration(self,config):
        result=select_configuration(config,self.speech,self.processing,self.learning,self.translation)
        result.analysis_enabled=self.learning;result.analysis_provider='local'
        result.translation_enabled=self.translation;result.translation_mode='fast';result.refinement_enabled=False
        return result


def inventory(plan,manager):
    specs=catalog();rows=[]
    for key in plan.identifiers:
        spec=specs[key];present=manager.availability(key)=='installed';saved=0
        if not present:
            for asset in spec.assets:
                file=manager.root/'downloads'/key/asset.name
                partial=file.with_suffix(file.suffix+'.part')
                candidate=file if file.is_file() else partial
                try:
                    if candidate.is_file():saved+=min(asset.size,candidate.stat().st_size)
                except OSError:pass
        rows.append(dict(id=key,size=spec.size,present=present,saved=saved))
    return rows


def disk_estimate(rows):
    missing=[row for row in rows if not row['present']]
    download=sum(row['size']-row['saved'] for row in missing)
    # Keep the existing component installer's staging reserve, including cache verification.
    reserve=max(download+max((r['size'] for r in missing),default=0)+512*1024**2,max((r['size']*2+100*1024**2 for r in missing),default=0)) if missing else 0
    return download,reserve


def format_bytes(value):return f'{value/1e9:.2f} GB' if value>=1e9 else f'{value/1e6:.0f} MB'


def nearest_existing(path):
    path=Path(path)
    while not path.exists() and path!=path.parent:path=path.parent
    return path


def component_percent(identifier,manager,fallback):
    """Weight multi-file transfers by actual saved bytes, not the last tiny file."""
    spec=catalog()[identifier];present=manager.path(identifier);saved=0;found=False
    for asset in spec.assets:
        cache=manager.root/'downloads'/identifier/asset.name
        options=[cache,cache.with_suffix(cache.suffix+'.part')]
        if present:options.insert(0,present.parent/asset.name)
        for candidate in options:
            try:
                if candidate.is_file():saved+=min(asset.size,candidate.stat().st_size);found=True;break
            except OSError:pass
    return min(99,int(saved*100/max(1,spec.size))) if found and fallback<100 else fallback
