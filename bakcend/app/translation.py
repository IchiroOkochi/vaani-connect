from __future__ import annotations

from dataclasses import dataclass

import torch
from IndicTransToolkit.processor import IndicProcessor
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

ENGLISH_CODE = "eng_Latn"


@dataclass
class TranslationService:
    """IndicTrans2 translation wrapper for backend usage."""

    device: str = "cuda" if torch.cuda.is_available() else "cpu"

    def __post_init__(self) -> None:
        self.ip = IndicProcessor(inference=True)

        self.en_indic_tokenizer = AutoTokenizer.from_pretrained(
            "ai4bharat/indictrans2-en-indic-dist-200M",
            trust_remote_code=True,
        )
        self.en_indic_model = AutoModelForSeq2SeqLM.from_pretrained(
            "ai4bharat/indictrans2-en-indic-dist-200M",
            trust_remote_code=True,
        ).to(self.device)

        self.indic_en_tokenizer = AutoTokenizer.from_pretrained(
            "ai4bharat/indictrans2-indic-en-dist-200M",
            trust_remote_code=True,
        )
        self.indic_en_model = AutoModelForSeq2SeqLM.from_pretrained(
            "ai4bharat/indictrans2-indic-en-dist-200M",
            trust_remote_code=True,
        ).to(self.device)

    def _run_translation(
        self,
        texts: list[str],
        src_lang: str,
        tgt_lang: str,
        model,
        tokenizer,
    ) -> list[str]:
        batch = self.ip.preprocess_batch(texts, src_lang=src_lang, tgt_lang=tgt_lang)
        inputs = tokenizer(
            batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
        ).to(self.device)

        with torch.no_grad():
            generated = model.generate(
                **inputs,
                num_beams=5,
                num_return_sequences=1,
                max_length=256,
            )

        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        return self.ip.postprocess_batch(decoded, lang=tgt_lang)

    def translate_text(self, text: str, src_lang: str, tgt_lang: str) -> str:
        if src_lang == ENGLISH_CODE:
            return self._run_translation(
                [text],
                src_lang,
                tgt_lang,
                self.en_indic_model,
                self.en_indic_tokenizer,
            )[0]

        if tgt_lang == ENGLISH_CODE:
            return self._run_translation(
                [text],
                src_lang,
                tgt_lang,
                self.indic_en_model,
                self.indic_en_tokenizer,
            )[0]

        english_intermediate = self._run_translation(
            [text],
            src_lang,
            ENGLISH_CODE,
            self.indic_en_model,
            self.indic_en_tokenizer,
        )
        return self._run_translation(
            english_intermediate,
            ENGLISH_CODE,
            tgt_lang,
            self.en_indic_model,
            self.en_indic_tokenizer,
        )[0]
