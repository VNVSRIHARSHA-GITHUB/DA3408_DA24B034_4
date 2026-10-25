"""BLIP captioning model wrapper (no Streamlit or Prometheus code)."""

import os

# CPU-only: hide any GPU before torch is imported.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import time

import torch
from PIL import Image
from transformers import BlipForConditionalGeneration, BlipProcessor

DEFAULT_MODEL = os.environ.get("CAPTION_MODEL", "Salesforce/blip-image-captioning-base")
DEVICE = torch.device("cpu")

# Stops repetition loops such as "a gi gi gi ..." (found via the
# caption_length_words histogram) without slowing decoding.
GENERATION_KWARGS = {
    "repetition_penalty": 1.3,
    "no_repeat_ngram_size": 2,
}


class Captioner:
    """Loads BLIP once; caption() turns one RGB PIL image into a sentence."""

    def __init__(self, model_name: str = DEFAULT_MODEL, max_new_tokens: int = 30):
        start = time.perf_counter()
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        self.processor = BlipProcessor.from_pretrained(model_name)
        self.model = BlipForConditionalGeneration.from_pretrained(model_name).to(DEVICE)
        self.model.eval()
        self.load_seconds = time.perf_counter() - start

    @property
    def num_threads(self) -> int:
        """CPU threads used by torch."""
        return torch.get_num_threads()

    @torch.inference_mode()
    def caption(self, image: Image.Image, num_beams: int = 1) -> str:
        """num_beams=1 is greedy decoding; >1 is beam search (slower on CPU)."""
        inputs = self.processor(images=image, return_tensors="pt").to(DEVICE)
        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=self.max_new_tokens,
            num_beams=num_beams,
            **GENERATION_KWARGS,
        )
        return self.processor.decode(output_ids[0], skip_special_tokens=True).strip()
