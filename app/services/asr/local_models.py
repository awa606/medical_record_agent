"""Resolve the deployed local snapshot before calling FunASR in offline mode."""
from pathlib import Path
import os

ALIASES = {
    'paraformer-zh': 'speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch',
    'paraformer-zh-streaming': 'speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online',
    'fsmn-vad': 'speech_fsmn_vad_zh-cn-16k-common-pytorch',
    'ct-punc': 'punc_ct-transformer_cn-en-common-vocab471067-large',
    'cam++': 'speech_campplus_sv_zh-cn_16k-common',
}


def offline() -> bool:
    return os.getenv('RECORD_PROVIDER_MODE') == 'edge' or os.getenv('HF_HUB_OFFLINE') == '1'


def resolve_model(model: str) -> str:
    if not offline():
        return model
    if Path(model).is_dir():
        return model
    name = ALIASES.get(model)
    root = Path(os.getenv('MODELSCOPE_CACHE', Path.home() / '.cache/modelscope'))
    if name:
        weights = 'campplus_cn_common.bin' if model == 'cam++' else 'model.pt'
        for candidate in (root/'iic'/name, root/'models'/f'iic--{name}'/'snapshots/master'):
            if (candidate/'configuration.json').is_file() and (candidate/weights).is_file():
                return str(candidate)
    raise RuntimeError(f'LOCAL_MODEL_MISSING: {model}; populate the configured cache before offline execution')
