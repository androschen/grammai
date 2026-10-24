"""Read-only, allowlisted accuracy settings audit. Does not load models or record audio."""
import argparse
import json
from pathlib import Path
from core.preferences import load_config, data_dir

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    config = load_config()
    names = ('backend','model_size','compute_type','cpu_threads','beam_size',
        'source_language','target_language','translation_mode','translation_enabled',
        'speech_detection','speech_max_seconds','speech_silence_seconds',
        'speech_overlap_seconds','noise_threshold','sample_rate','capture_chunk_seconds',
        'analysis_enabled','analysis_provider','analysis_context_sentences')
    report = {'preferences_path': str(data_dir()/'preferences.json'),
        'preferences_exist': (data_dir()/'preferences.json').is_file(),
        'settings': {name:getattr(config,name) for name in names},
        'speech_model': Path(config.vulkan_model).name if config.backend == 'vulkan' else config.model_size,
        'review_model': Path(config.analysis_gguf).name,
        'vocabulary_hint_configured': bool(config.speech_prompt)}
    # A Windows Store launcher can redirect AppData despite the apparent path.
    # Record the actual opened file so an audit cannot confuse the two profiles.
    if report['preferences_exist']:
        import os
        if os.name == 'nt':
            import ctypes, msvcrt
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
            with (data_dir()/'preferences.json').open('rb') as handle:
                buffer = ctypes.create_unicode_buffer(32768)
                length = kernel.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(handle.fileno()), buffer, len(buffer), 0)
                if not length or length >= len(buffer):
                    raise ctypes.WinError(ctypes.get_last_error())
                report['physical_preferences_path'] = buffer.value
    Path(args.report).write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__ == '__main__':
    main()
