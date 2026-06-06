import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path

import numpy as np
import openai
import requests
import torch
from dotenv import load_dotenv
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoProcessor


class MenuAIProcessor:
    """리뷰 요약, 텍스트 벡터화, 메뉴 사진 매칭을 담당한다."""

    _shared_vector_model = None
    _shared_siglip_model = None
    _shared_siglip_processor = None

    def __init__(self, api_key=None):
        load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
        load_dotenv()

        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")

        self.api_key = api_key
        self.llm_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = None
        self.max_reviews_for_llm = int(os.getenv("MAX_REVIEWS_FOR_LLM", "20"))
        self.siglip_model_name = os.getenv(
            "SIGLIP_MODEL",
            "google/siglip-base-patch16-256-multilingual",
        )
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.vector_model = None

    async def analyze_reviews(self, menu_name, reviews) -> dict:
        """AsyncOpenAI 기반 리뷰 분석. FastAPI에서는 이 메서드를 await해서 사용한다."""
        reviews = self._limit_reviews(reviews)
        prompt = self._build_review_prompt(menu_name, reviews)

        try:
            raw = await self._generate_summary_with_llm(prompt)
            raw = self._extract_json(raw)
            return json.loads(raw)
        except Exception as exc:
            return self._handle_ai_error(exc)

    def _limit_reviews(self, reviews):
        """LLM token limit 방지를 위해 리뷰 입력을 최대 20개로 제한한다."""
        if reviews is None:
            return []

        if isinstance(reviews, list):
            return reviews[: self.max_reviews_for_llm]

        return reviews

    def _build_review_prompt(self, menu_name, reviews) -> str:
        review_text = "\n".join(self._normalize_review_texts(reviews))

        return f"""
당신은 음식점 리뷰 분석 전문가입니다.

메뉴 '{menu_name}'에 대한 리뷰:
{review_text}

아래 규칙을 반드시 지켜 JSON으로만 응답하세요.

[분석 기준]
- 핵심 내용만 간결하게 요약
- 중복 내용 제거
- 감정 표현은 객관적으로 정리

[출력 형식]
{{
    "level_1": {{
        "pros": "대표 장점 1줄 요약",
        "cons": "대표 단점 1줄 요약"
    }},
    "level_2": [
        {{ "content": "구체적 장점", "type": "PROS" }},
        {{ "content": "구체적 단점", "type": "CONS" }}
    ]
}}
"""

    def _normalize_review_texts(self, reviews):
        """문자열 리스트와 crawler 리뷰 dict 리스트를 모두 프롬프트용 텍스트로 정리한다."""
        if reviews is None:
            return []

        if isinstance(reviews, str):
            return [reviews]

        if not isinstance(reviews, list):
            return [str(reviews)]

        normalized = []
        for review in reviews:
            if isinstance(review, dict):
                content = review.get("content", "")
            else:
                content = review

            content = str(content).strip()
            if content:
                normalized.append(content)

        return normalized

    async def _generate_summary_with_llm(self, prompt: str) -> str:
        self._ensure_openai_client()

        response = await self.client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )

        return response.choices[0].message.content.strip()

    def _ensure_openai_client(self):
        """LLM 요약이 필요할 때만 OpenAI 클라이언트를 생성한다."""
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set.")

        if self.client is None:
            self.client = openai.AsyncOpenAI(api_key=self.api_key)

    def match_photo(self, menu_name, image_urls) -> str:
        """
        google/siglip-base-patch16-256-multilingual 기반 메뉴명-사진 매칭.
        이미지 URL들을 실제로 열어 메뉴명과 가장 유사한 사진 URL을 반환한다.
        """
        if not image_urls:
            return "default_url"

        self._ensure_siglip_model()

        best_score = -1.0
        best_url = image_urls[0]

        for url in image_urls:
            image = self._load_image_from_url(url)
            if image is None:
                continue

            score = self._siglip_similarity(menu_name, image)
            if score > best_score:
                best_score = score
                best_url = url

        return best_url

    def _ensure_siglip_model(self):
        """SigLIP 모델을 lazy loading해서 앱 시작 시간을 줄인다."""
        if MenuAIProcessor._shared_siglip_model is None:
            MenuAIProcessor._shared_siglip_processor = AutoProcessor.from_pretrained(
                self.siglip_model_name
            )
            MenuAIProcessor._shared_siglip_model = AutoModel.from_pretrained(
                self.siglip_model_name
            ).to(self.device)
            MenuAIProcessor._shared_siglip_model.eval()

        self.siglip_processor = MenuAIProcessor._shared_siglip_processor
        self.siglip_model = MenuAIProcessor._shared_siglip_model

    def _load_image_from_url(self, url):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGB")
        except Exception:
            return None

    def _siglip_similarity(self, menu_name, image) -> float:
        labels = [
            menu_name,
            f"{menu_name} 음식 사진",
            f"{menu_name} 메뉴 사진",
        ]
        inputs = self.siglip_processor(
            text=labels,
            images=image,
            padding="max_length",
            return_tensors="pt",
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}

        with torch.no_grad():
            outputs = self.siglip_model(**inputs)

        scores = torch.sigmoid(outputs.logits_per_image).squeeze(0)
        return float(scores.max().item())

    def evaluate_photo_matching(self, test_cases):
        """
        이미지-텍스트 매칭 정확도 검증용 함수.
        test_cases 예:
        [
            {
                "menu_name": "김치찌개",
                "image_urls": ["url1", "url2"],
                "expected_url": "url1"
            }
        ]
        """
        if not test_cases:
            return {
                "total": 0,
                "correct": 0,
                "accuracy": 0.0,
                "results": [],
            }

        results = []
        correct = 0

        for case in test_cases:
            predicted_url = self.match_photo(
                case.get("menu_name", ""),
                case.get("image_urls", []),
            )
            expected_url = case.get("expected_url")
            is_correct = predicted_url == expected_url

            if is_correct:
                correct += 1

            results.append(
                {
                    "menu_name": case.get("menu_name", ""),
                    "predicted_url": predicted_url,
                    "expected_url": expected_url,
                    "is_correct": is_correct,
                }
            )

        total = len(test_cases)

        return {
            "total": total,
            "correct": correct,
            "accuracy": correct / total,
            "results": results,
        }

    def vectorize_text(self, text_list):
        """SBERT 기반 텍스트 임베딩을 생성한다."""
        self._ensure_vector_model()
        embeddings = self.vector_model.encode(text_list)
        return embeddings.tolist()

    def search_similar(self, query, text_list, top_k=5):
        """텍스트 유사도 기반 검색."""
        if not query or not text_list or top_k <= 0:
            return []

        self._ensure_vector_model()
        query_vec = self.vector_model.encode([query])[0]
        text_vecs = self.vector_model.encode(text_list)

        scores = []

        for i, vec in enumerate(text_vecs):
            score = self._cosine_similarity(query_vec, vec)
            scores.append(
                {
                    "text": text_list[i],
                    "score": float(score),
                }
            )

        scores.sort(key=lambda x: x["score"], reverse=True)

        return scores[:top_k]

    def _ensure_vector_model(self):
        """SBERT 모델을 텍스트 벡터 기능이 필요할 때만 로딩한다."""
        if MenuAIProcessor._shared_vector_model is None:
            MenuAIProcessor._shared_vector_model = SentenceTransformer(
                "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
            )

        self.vector_model = MenuAIProcessor._shared_vector_model

    def _extract_json(self, text):
        """LLM 응답에서 JSON 블록만 추출한다."""
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        text = text.strip()

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group()

        return text

    def _empty_review_result(self):
        return {
            "level_1": {"pros": "", "cons": ""},
            "level_2": [],
        }

    def _handle_ai_error(self, exc):
        if os.getenv("AI_DEBUG") == "1":
            print(f"[MenuAIProcessor] analyze_reviews failed: {exc}", file=sys.stderr)

        return self._empty_review_result()

    def _cosine_similarity(self, vec1, vec2):
        """코사인 유사도 계산."""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        denominator = np.linalg.norm(vec1) * np.linalg.norm(vec2)

        if denominator == 0:
            return 0.0

        return np.dot(vec1, vec2) / denominator
