from __future__ import annotations

import re

from app.schemas.asr import ASREvaluationResult


PUNCTUATION_PATTERN = re.compile(r"[\s，。！？、；：,.!?;:\-—（）()《》<>\"'“”‘’\[\]【】]+")
SPEAKER_LINE_PATTERN = re.compile(r"^发言人[12]\s*(?:\d{1,2}:\d{2})?\s*$")
LINE_PREFIX_PATTERN = re.compile(r"^(?:发言人[12]\s+)?(?:\d{1,2}:\d{2})\s*")

KeywordSpec = str | dict[str, object]


class ASREvaluator:
    def clean_ground_truth_text(self, text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if SPEAKER_LINE_PATTERN.match(line):
                continue
            line = LINE_PREFIX_PATTERN.sub("", line).strip()
            if line:
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    def normalize_text(self, text: str) -> str:
        return PUNCTUATION_PATTERN.sub("", text or "")

    def edit_distance(self, reference: str, hypothesis: str, *, clean_speaker_labels: bool = True) -> int:
        reference_text = self.clean_ground_truth_text(reference) if clean_speaker_labels else reference
        ref = self.normalize_text(reference_text)
        hyp = self.normalize_text(hypothesis)
        if not ref:
            return len(hyp)
        if not hyp:
            return len(ref)

        previous = list(range(len(hyp) + 1))
        for i, ref_char in enumerate(ref, start=1):
            current = [i]
            for j, hyp_char in enumerate(hyp, start=1):
                cost = 0 if ref_char == hyp_char else 1
                current.append(
                    min(
                        previous[j] + 1,
                        current[j - 1] + 1,
                        previous[j - 1] + cost,
                    )
                )
            previous = current
        return previous[-1]

    def cer(
        self,
        reference: str,
        hypothesis: str,
        *,
        clean_speaker_labels: bool = True,
    ) -> tuple[float, int, int]:
        reference_text = self.clean_ground_truth_text(reference) if clean_speaker_labels else reference
        normalized_reference = self.normalize_text(reference_text)
        reference_length = len(normalized_reference)
        distance = self.edit_distance(
            reference,
            hypothesis,
            clean_speaker_labels=clean_speaker_labels,
        )
        if reference_length == 0:
            return (0.0 if distance == 0 else 1.0, reference_length, distance)
        return distance / reference_length, reference_length, distance

    def keyword_metrics(
        self,
        expected_keywords: list[KeywordSpec],
        recognized_text: str,
    ) -> dict[str, object]:
        keyword_specs = self._normalize_keyword_specs(expected_keywords)
        expected = [name for name, _aliases in keyword_specs]
        normalized_text = self.normalize_text(recognized_text)
        recognized = []
        for name, aliases in keyword_specs:
            if any(self.normalize_text(alias) in normalized_text for alias in aliases):
                recognized.append(name)
        missing = [keyword for keyword in expected if keyword not in recognized]
        recall = len(recognized) / len(expected) if expected else 0.0
        return {
            "expected": expected,
            "recognized": recognized,
            "missing": missing,
            "keyword_recall": recall,
        }

    def evaluate(
        self,
        *,
        audio_id: str,
        engine: str,
        ground_truth_text: str,
        recognized_text: str,
        expected_keywords: list[KeywordSpec],
        clean_speaker_labels: bool = True,
    ) -> ASREvaluationResult:
        cer_value, reference_length, distance = self.cer(
            ground_truth_text,
            recognized_text,
            clean_speaker_labels=clean_speaker_labels,
        )
        keyword_result = self.keyword_metrics(expected_keywords, recognized_text)
        return ASREvaluationResult(
            audio_id=audio_id,
            engine=engine,
            cer=cer_value,
            reference_length=reference_length,
            edit_distance=distance,
            keyword_recall=float(keyword_result["keyword_recall"]),
            medical_keywords={
                "expected": keyword_result["expected"],
                "recognized": keyword_result["recognized"],
                "missing": keyword_result["missing"],
            },
        )

    def _normalize_keyword_specs(
        self,
        expected_keywords: list[KeywordSpec],
    ) -> list[tuple[str, list[str]]]:
        specs: list[tuple[str, list[str]]] = []
        seen: set[str] = set()
        for item in expected_keywords:
            name: str | None = None
            aliases: list[str] = []
            if isinstance(item, str):
                name = item.strip()
                aliases = [name]
            elif isinstance(item, dict):
                raw_name = item.get("name")
                if isinstance(raw_name, str):
                    name = raw_name.strip()
                raw_aliases = item.get("aliases")
                if isinstance(raw_aliases, list):
                    aliases = [
                        alias.strip()
                        for alias in raw_aliases
                        if isinstance(alias, str) and alias.strip()
                    ]
            if not name or name in seen:
                continue
            seen.add(name)
            if name not in aliases:
                aliases.insert(0, name)
            specs.append((name, list(dict.fromkeys(aliases))))
        return specs
