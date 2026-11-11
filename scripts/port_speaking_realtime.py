"""Vendor the supplied PolyInterview LiveTalking implementation without editing it."""
import hashlib
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/livetalking"
TARGET = ROOT / "backend/speaking/vendor/livetalking"


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    replacements = {
        "from logger import logger as mylogger": "from .logger import logger as mylogger",
        "from logger import logger": "from .logger import logger",
        "from basereal import BaseReal, _gpu_rgb_to_yuv420p": "from .basereal import BaseReal, _gpu_rgb_to_yuv420p",
        "from basereal import BaseReal": "from typing import Any as BaseReal",
        "from baseasr import BaseASR": "from .baseasr import BaseASR",
        "from gpu_inference_scheduler import InferenceRequest": "from .gpu_inference_scheduler import InferenceRequest",
        "from lipasr import LipASR": "from .lipasr import LipASR",
        "from wav2lip.models import Wav2Lip": "from ..wav2lip import Wav2Lip",
        "from wav2lip import audio": "from . import audio",
    }
    provenance = []
    for name in ("webrtc.py", "basereal.py", "baseasr.py", "lipasr.py", "lipreal.py", "gpu_inference_scheduler.py", "wav2lip/audio.py", "wav2lip/hparams.py"):
        original = (SOURCE / name).read_bytes()
        content = original.decode("utf-8-sig").replace("\r\n", "\n")
        for old, new in replacements.items():
            content = content.replace(old, new)
        if name == "basereal.py":
            import_line = next(line for line in content.splitlines() if line.startswith("from ttsreal import"))
            content = content.replace(import_line, "from ...live_tts import StreamingTTS")
            begin = content.index('        if opt.tts == "edgetts":')
            end = content.index("        self.speaking = False", begin)
            content = content[:begin] + "        self.tts = StreamingTTS(opt, self)\n\n" + content[end:]
        destination = TARGET / Path(name).name
        destination.write_text(content, encoding="utf-8")
        provenance.append({"source": "backend/livetalking/" + name,
                           "source_sha256": hashlib.sha256(original).hexdigest(),
                           "vendored": destination.relative_to(ROOT).as_posix(),
                           "vendored_sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
    (TARGET / "__init__.py").write_text('"""PolyInterview LiveTalking with package imports and a hosted TTS adapter."""\n', encoding="utf-8")
    (TARGET / "logger.py").write_text('import logging\nlogger = logging.getLogger("polyspeak.livetalking")\n', encoding="utf-8")
    evaluation_source = ROOT / "backend/services/final_evaluation_service.py"
    tree = ast.parse(evaluation_source.read_text(encoding="utf-8-sig"))
    original_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FinalEvaluationService")
    methods = [node for node in original_class.body if isinstance(node, ast.FunctionDef) and node.name in ("_aggregate_aspects", "_aggregate_features")]
    portable_class = ast.ClassDef(name="PolyInterviewReportAggregation", bases=[], keywords=[], body=methods, decorator_list=[])
    aggregation = "# Pure aggregation methods copied from PolyInterview FinalEvaluationService.\nfrom typing import Dict, Any\n\n" + ast.unparse(ast.fix_missing_locations(portable_class)) + "\n"
    evaluation_target = TARGET.parent / "evaluation_aggregation.py"
    evaluation_target.write_text(aggregation, encoding="utf-8")
    provenance.append({"source": "backend/services/final_evaluation_service.py", "source_sha256": hashlib.sha256(evaluation_source.read_bytes()).hexdigest(), "vendored": evaluation_target.relative_to(ROOT).as_posix(), "methods": [node.name for node in methods]})
    (TARGET / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print("Vendored original PolyInterview media pipeline; protected source unchanged:", len(provenance), "files")


if __name__ == "__main__":
    main()
