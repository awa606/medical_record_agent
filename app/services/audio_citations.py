"""Relate clinical-sentence citations to the source ASR turns and their actual clocks."""
from __future__ import annotations

import math
import re
from typing import Any

from app.schemas import SourceSpan
from app.services.asr.speaker_role_policy import normalize_role
from app.services.clinical_facts import clinical_segment_contexts, comparison_without_role, split_clinical_segments


def quote_text(value: str) -> str:
    return re.sub(r"[\s，。！？!?、,]+", "", comparison_without_role(value))


def _audio_time(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _segment_time(segment: dict[str, Any], key: str) -> float | None:
    value = segment.get(f"{key}_time")
    return _audio_time(segment.get(key) if value is None else value)


class AudioCitationIndex:
    """Relate zero-based model sentence numbers to ASR turns only when their texts align."""

    def __init__(self, conversation: str, segments: list[dict[str, Any]], *, persisted: bool = False):
        self.persisted = persisted
        self.sentences = clinical_segment_contexts(conversation)
        self.rows = []
        self.by_id = {}
        owners = []
        normalized_sentences = []
        for index, segment in enumerate(segments):
            text = str(segment.get("text") or "")
            segment_id = segment.get("segment_id") or (None if persisted else f"segment-{index}")
            start = _segment_time(segment, "start")
            end = _segment_time(segment, "end")
            if start is not None and end is not None and end < start:
                start = end = None
            row = {"segment_id": segment_id, "index": index, "start_time": start, "end_time": end,
                   "speaker_id": segment.get("speaker_id") or segment.get("speaker"),
                   "role": segment.get("role"), "text": text}
            self.rows.append(row)
            self.by_id[segment_id] = None if segment_id in self.by_id else row
            for sentence in split_clinical_segments(text):
                owners.append(row)
                normalized_sentences.append(quote_text(sentence))
        self.owners = owners if normalized_sentences == [quote_text(s.text) for s in self.sentences] else []

    def match(self, span: SourceSpan) -> tuple[dict, SourceSpan] | None:
        quote = quote_text(span.text)
        if not quote:
            return None
        contexts = clinical_segment_contexts(span.text)
        role = normalize_role(contexts[0].speaker) if contexts else None
        candidates = self.rows
        if span.index is not None:
            if not 0 <= span.index < len(self.sentences):
                return None
            sentence = self.sentences[span.index]
            if quote not in quote_text(sentence.text):
                return None
            if self.owners:
                candidates = [self.owners[span.index]]
            elif self.persisted and (
                sum(quote in quote_text(item.text) for item in self.sentences) != 1
                or sum(quote in quote_text(row["text"]) for row in self.rows) != 1
            ):
                return None
            sentence_role = normalize_role(sentence.speaker)
            if role and sentence_role and role != sentence_role:
                return None
            role = role or sentence_role
        matches = [row for row in candidates
                   if quote in quote_text(row["text"])
                   and (span.segment_id is None or row["segment_id"] == span.segment_id)
                   and (role is None or not row["role"] or normalize_role(row["role"]) == role)]
        if len(matches) != 1:
            return None
        row = matches[0]
        if row["segment_id"] is not None and self.by_id[row["segment_id"]] is None:
            return None
        start, end = row["start_time"], row["end_time"]
        if self.persisted and ((span.start_time is not None and start is None) or (span.end_time is not None and end is None)):
            return None
        supplied = [v for v in (span.start_time, span.end_time) if v is not None]
        if any(_audio_time(v) is None or (start is not None and v < start)
               or (end is not None and v > end) for v in supplied):
            return None
        if span.start_time is not None and span.end_time is not None and span.start_time > span.end_time:
            return None
        verified = span.model_copy(update={"segment_id": row["segment_id"],
            "start_time": span.start_time if span.start_time is not None and start is not None else start,
            "end_time": span.end_time if span.end_time is not None and end is not None else end})
        return row, verified

    def resolve(self, span: SourceSpan) -> SourceSpan | None:
        matched = self.match(span)
        return matched[1] if matched is not None else None
