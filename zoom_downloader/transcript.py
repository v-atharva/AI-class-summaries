"""
Transcript parsing and conversion helpers for VTT caption files.

Design note:
- Keep text conversion functions small and composable.
- Use one parser/formatter class so behavior can be reused from CLI or other callers.
"""

import html
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VTTCue:
    """
    Parsed caption cue unit.

    Variables:
    - timestamp
      usage: original cue timestamp line from VTT.
    - text
      usage: cleaned caption text corresponding to the timestamp.
    """

    timestamp: str
    text: str


class TranscriptConverter:
    """
    Parse and convert transcript payloads (VTT -> output text formats).

    Variables:
    - tag_re
      usage: regex used to remove caption HTML tags during normalization.
    """

    def __init__(self):
        """
        Initializes transcript conversion state, including the reusable pattern used to strip caption tags.
        """
        self.tag_re = re.compile(r"<[^>]+>")

    def _clean_caption_line(self, line: str) -> str:
        """
        Variables:
            • line
                usage: raw caption line that may include markup, entities, and irregular spacing.
            • text
                usage: progressively cleaned caption text after tag removal and entity decoding.

        Cleans a caption line by removing markup, decoding entities, and normalizing whitespace to readable plain text.
        """
        text = self.tag_re.sub("", line)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def parse_vtt_cues(self, vtt_text: str) -> list[VTTCue]:
        """
        Variables:
            • vtt_text
                usage: raw VTT transcript payload parsed into structured cue records.
            • lines
                usage: normalized transcript lines iterated sequentially during cue parsing.
            • cues
                usage: parsed timestamp-and-text cue records returned for downstream conversions.
            • i
                usage: moving line index used to traverse transcript content while constructing cues.
            • line
                usage: current normalized line evaluated to detect cue metadata and content boundaries.
            • timestamp
                usage: current cue timestamp line captured for the associated caption text block.
            • text_lines
                usage: cleaned caption lines collected for the current cue before joining.
            • cleaned
                usage: normalized caption fragment appended when non-empty.
            • cue_text
                usage: final joined caption text used to create a parsed cue object.
        Functions:
            self._clean_caption_line - normalizes raw caption lines before they are merged into cue text.
            VTTCue - constructs parsed cue objects from extracted timestamp and text values.

        Parses VTT content into ordered cue objects while handling optional cue identifiers and skipping non-caption metadata lines.
        """
        lines = vtt_text.replace("\ufeff", "").splitlines()
        cues: list[VTTCue] = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            if not line or line.upper() == "WEBVTT" or line.startswith("NOTE"):
                i += 1
                continue

            timestamp = None
            if "-->" in line:
                timestamp = line
                i += 1
            elif i + 1 < len(lines) and "-->" in lines[i + 1]:
                timestamp = lines[i + 1].strip()
                i += 2
            else:
                i += 1
                continue

            text_lines: list[str] = []
            while i < len(lines) and lines[i].strip():
                cleaned = self._clean_caption_line(lines[i].strip())
                if cleaned:
                    text_lines.append(cleaned)
                i += 1

            cue_text = " ".join(text_lines).strip()
            if cue_text:
                cues.append(VTTCue(timestamp=timestamp, text=cue_text))

        return cues

    def vtt_to_paragraph(self, vtt_text: str) -> str:
        """
        Variables:
            • vtt_text
                usage: raw VTT transcript payload converted into paragraph-form output.
            • cues
                usage: parsed cue sequence used as the source for paragraph assembly.
            • chunks
                usage: ordered caption fragments appended when they are not consecutive duplicates.
            • prev
                usage: previously appended caption text used to suppress immediate duplicates.
            • cue
                usage: iterated cue record providing caption text for deduplicated paragraph assembly.
            • paragraph
                usage: joined paragraph text normalized before final return.
        Functions:
            self.parse_vtt_cues - parses raw VTT content into cue objects used for paragraph generation.

        Converts parsed VTT cues into a single deduplicated paragraph without timestamp markers.
        """
        cues = self.parse_vtt_cues(vtt_text)
        chunks: list[str] = []
        prev: str | None = None

        for cue in cues:
            if cue.text != prev:
                chunks.append(cue.text)
                prev = cue.text

        paragraph = " ".join(chunks).strip()
        return re.sub(r"\s+", " ", paragraph)

    def vtt_to_timestamped_txt(self, vtt_text: str) -> str:
        """
        Variables:
            • vtt_text
                usage: raw VTT transcript payload converted into timestamped plain text.
            • cues
                usage: parsed cue sequence used to create timestamp-and-text output blocks.
            • blocks
                usage: formatted cue blocks joined with blank lines for readable transcript output.
            • cue
                usage: iterated cue record referenced while creating each formatted output block.
        Functions:
            self.parse_vtt_cues - parses raw VTT content into cue objects used for timestamped formatting.

        Converts VTT cues into timestamped plain text blocks separated by blank lines for readability.
        """
        cues = self.parse_vtt_cues(vtt_text)
        blocks = [f"{cue.timestamp}\n{cue.text}" for cue in cues]
        return "\n\n".join(blocks).strip() + "\n"


DEFAULT_TRANSCRIPT_CONVERTER = TranscriptConverter()


def parse_vtt_cues(vtt_text):
    """
    Variables:
        • vtt_text
            usage: raw VTT transcript payload forwarded to the shared converter.
        • cues
            usage: parsed cue objects converted into tuple output for compatibility with older callers.
        • cue
            usage: iterated parsed cue converted into timestamp-and-text tuple form.
    Functions:
        DEFAULT_TRANSCRIPT_CONVERTER.parse_vtt_cues - delegates cue parsing to the shared transcript converter instance.

    Provides a backward-compatible wrapper that returns parsed cues as timestamp-and-text tuples.
    """
    cues = DEFAULT_TRANSCRIPT_CONVERTER.parse_vtt_cues(vtt_text)
    return [(cue.timestamp, cue.text) for cue in cues]


def vtt_to_paragraph(vtt_text):
    """
    Variables:
        • vtt_text
            usage: raw VTT transcript payload forwarded to the shared converter.
    Functions:
        DEFAULT_TRANSCRIPT_CONVERTER.vtt_to_paragraph - delegates paragraph conversion to the shared transcript converter instance.

    Provides a backward-compatible wrapper that converts VTT text into paragraph-form transcript output.
    """
    return DEFAULT_TRANSCRIPT_CONVERTER.vtt_to_paragraph(vtt_text)


def vtt_to_timestamped_txt(vtt_text):
    """
    Variables:
        • vtt_text
            usage: raw VTT transcript payload forwarded to the shared converter.
    Functions:
        DEFAULT_TRANSCRIPT_CONVERTER.vtt_to_timestamped_txt - delegates timestamped conversion to the shared transcript converter instance.

    Provides a backward-compatible wrapper that converts VTT text into timestamped plain-text output.
    """
    return DEFAULT_TRANSCRIPT_CONVERTER.vtt_to_timestamped_txt(vtt_text)
