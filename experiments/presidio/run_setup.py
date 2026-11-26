"""Run ONE setup over ONE dataset in its own process, so time and peak memory belong to it alone.

    python run_setup.py <ours|lg|lg_ctx|sm|xx> <dev|selftest>

Writes out/<setup>.<dataset>.json: spans as offsets (no record text) plus timings.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time

import common

MODELS = {"lg": "en_core_web_lg", "lg_ctx": "en_core_web_lg", "sm": "en_core_web_sm", "xx": "xx_ent_wiki_sm"}
INFO_TYPES = ("CONDITION", "DISTRICT", "GENDER")  # ours: never replaced, so not "flagged"


def network_is_off() -> bool:
    """True inside `unshare -n`: the only network interface left is loopback. Nothing is sent to find out."""
    with open("/proc/net/dev", encoding="ascii") as fh:
        interfaces = [line.split(":", 1)[0].strip() for line in fh if ":" in line]
    return all(name == "lo" for name in interfaces)


def peak_mb() -> float:
    with open("/proc/self/status") as fh:
        return round(next(int(l.split()[1]) for l in fh if l.startswith("VmHWM")) / 1024, 1)


def load_ours():
    from aegis.detect import detect_file

    def run(records):
        return [[(f["path"], f["start"], f["end"], f["type"], 1.0, "aegis") for f in res["findings"]
                 if f["type"] not in INFO_TYPES] for res in detect_file(records)]
    return run, {}


def load_presidio(setup: str):
    # EmailRecognizer uses tldextract, which tries to download the public suffix list and, offline, falls back
    # to the copy inside the package. With the network off that works but logs a long traceback: hide the log.
    logging.getLogger("tldextract").setLevel(logging.CRITICAL)
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import (InAadhaarRecognizer, InGstinRecognizer, InPanRecognizer,
                                                          InPassportRecognizer, InVehicleRegistrationRecognizer,
                                                          InVoterRecognizer)
    if setup in ("lg", "lg_ctx"):
        engine = AnalyzerEngine()  # the true default: en_core_web_lg, default recognizers, threshold 0
    else:
        # same defaults, only the spaCy model swapped
        from presidio_analyzer.nlp_engine import NerModelConfiguration, SpacyNlpEngine
        default = NlpEngineProvider().create_engine()
        nlp = SpacyNlpEngine(models=[{"lang_code": "en", "model_name": MODELS[setup]}],
                             ner_model_configuration=default.ner_model_configuration)
        engine = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
    enabled_before = sorted({r.name for r in engine.registry.recognizers})
    # all six Indian recognizers ship with enabled: false, so they are added by hand
    for cls in (InPanRecognizer, InAadhaarRecognizer, InVehicleRegistrationRecognizer, InPassportRecognizer,
                InVoterRecognizer, InGstinRecognizer):
        engine.registry.add_recognizer(cls())
    info = {"model": MODELS[setup], "model_version": engine.nlp_engine.nlp["en"].meta["version"],
            "default_recognizers": enabled_before,
            "added_by_hand": sorted({r.name for r in engine.registry.recognizers} - set(enabled_before))}

    def run(records):
        out = []
        for record in records:
            spans = []
            for f in record["fields"]:
                if not f["value"].strip():
                    continue
                words = None
                if setup == "lg_ctx" and f["context"]:  # column header / JSON key as outside context words
                    words = [w.casefold() for w in re.split(r"[\W_]+|(?<=[a-z])(?=[A-Z])", f["context"]) if w]
                for r in engine.analyze(text=f["value"], language="en", context=words):
                    who = (r.recognition_metadata or {}).get("recognizer_name", "?")
                    spans.append((f["path"], r.start, r.end, r.entity_type, round(r.score, 3), who))
            out.append(sorted(spans))
        return out
    return run, info


def main() -> int:
    setup, dataset = sys.argv[1], sys.argv[2]
    files = common.dev_files() if dataset == "dev" else common.selftest_files()
    offline = network_is_off()
    t0 = time.perf_counter()
    run, info = load_ours() if setup == "ours" else load_presidio(setup)
    t1 = time.perf_counter()
    loaded_mb = peak_mb()
    spans = {}
    for _, records in files:
        for record, found in zip(records, run(records)):
            spans[record["record_id"]] = found
    t2 = time.perf_counter()
    result = {"setup": setup, "dataset": dataset, "network_off": offline, "load_s": round(t1 - t0, 2),
              "analyze_s": round(t2 - t1, 2), "loaded_mb": loaded_mb,
              "peak_mb": peak_mb(), "cpus": len(os.sched_getaffinity(0)),
              "files": len(files), "info": info, "spans": spans}
    common.OUT.mkdir(exist_ok=True)
    (common.OUT / f"{setup}.{dataset}.json").write_text(json.dumps(result), encoding="utf-8")
    print(f"{setup:7} {dataset:9} offline={offline} cpus={result['cpus']} load={result['load_s']}s "
          f"analyze={result['analyze_s']}s loaded={loaded_mb}MB peak={result['peak_mb']}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
