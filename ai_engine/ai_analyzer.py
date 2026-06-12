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

    async def extract_menu_names_from_reviews(self, restaurant_name, reviews) -> dict:
        """리뷰 본문에서 식당별 메뉴 후보를 추출한다."""
        reviews = self._limit_reviews(reviews)
        prompt = self._build_menu_extraction_prompt(restaurant_name, reviews)

        try:
            raw = await self._generate_summary_with_llm(prompt)
            raw = self._extract_json(raw)
            result = json.loads(raw)
            return self._normalize_menu_extraction_result(result)
        except Exception as exc:
            return self._handle_menu_extraction_error(exc)

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
당신은 음식점 메뉴 리뷰 분석 전문가입니다.

메뉴명: {menu_name}

리뷰:
{review_text}

규칙:
- 메뉴의 맛, 양, 가격, 식감 등 메뉴 자체와 관련된 내용만 요약
- level_1은 개별 리뷰 한 문장을 복사하지 말고 모든 리뷰를 종합한 대표 장점/단점으로 작성
- 리뷰에 없는 내용은 만들지 않음
- 중복 내용을 제거하고 원문을 그대로 복사하지 않음
- 반드시 순수 JSON만 출력하고, 설명문/마크다운은 금지
- "type"은 반드시 "PROS" 또는 "CONS"만 사용
- "level_2"는 최대 4개까지만 작성

출력 형식:
{{
    "level_1": {{
        "pros": "대표 장점 1문장",
        "cons": "대표 단점 1문장"
    }},
    "level_2": [
        {{ "content": "구체적 장점 요약", "type": "PROS" }},
        {{ "content": "구체적 단점 요약", "type": "CONS" }}
    ]
}}
"""

    def _build_menu_extraction_prompt(self, restaurant_name, reviews) -> str:
        review_text = "\n".join(self._normalize_review_texts(reviews))

        return f"""
당신은 음식점 리뷰에서 실제 메뉴명을 추출하는 정보 정리 도구입니다.

식당명: {restaurant_name}

리뷰:
{review_text}

규칙:
- 리뷰에 직접 언급된 음식/메뉴 이름만 추출
- 식당명, 지점명, 감정 표현, 맛 표현, 재료명만 단독으로 쓰인 단어는 제외
- "맛있다", "매콤하다", "양이 많다"처럼 메뉴명이 아닌 표현은 제외
- 같은 메뉴는 하나로 합치고, 대표 표기는 가장 자연스러운 한국어 메뉴명으로 작성
- 확실하지 않은 후보는 제외
- 최대 10개까지만 추출
- 반드시 순수 JSON만 출력하고, 설명문/마크다운은 금지

출력 형식:
{{
    "restaurant_name": "{restaurant_name}",
    "menus": [
        {{
            "menu_name": "리뷰에서 확인된 메뉴명",
            "evidence": "해당 메뉴명을 판단한 짧은 근거",
            "confidence": 0.0
        }}
    ]
}}
"""

    def _normalize_menu_extraction_result(self, result):
        restaurant_name = str(result.get("restaurant_name", "")).strip()
        menus = result.get("menus", [])

        if not isinstance(menus, list):
            menus = []

        normalized_menus = []
        seen = set()

        for item in menus[:10]:
            if not isinstance(item, dict):
                continue

            menu_name = str(item.get("menu_name", "")).strip()
            if not menu_name or menu_name in seen:
                continue

            seen.add(menu_name)

            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0

            normalized_menus.append({
                "menu_name": menu_name,
                "evidence": str(item.get("evidence", "")).strip(),
                "confidence": max(0.0, min(1.0, confidence)),
            })

        return {
            "restaurant_name": restaurant_name,
            "menus": normalized_menus,
        }

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

    def match_menu_photos(
        self,
        menu_names,
        image_urls,
        filter_food=True,
        food_threshold=0.5,
        match_threshold=0.5,
        unique_photos=True,
    ):
        """메뉴명 후보마다 가장 잘 맞는 음식 사진 URL을 매칭한다."""
        if not menu_names or not image_urls:
            return []

        self._ensure_siglip_model()

        candidate_urls = image_urls
        if filter_food:
            candidate_urls = self.filter_food_photos(
                image_urls,
                threshold=food_threshold,
                return_scores=False,
            )

        if not candidate_urls:
            return []

        image_cache = {}
        for url in candidate_urls:
            image = self._load_image_from_url(url)
            if image is not None:
                image_cache[url] = image

        if not image_cache:
            return []

        unique_menu_names = []
        seen_menu_names = set()

        for menu_name in menu_names:
            menu_name = str(menu_name).strip()
            if not menu_name or menu_name in seen_menu_names:
                continue

            seen_menu_names.add(menu_name)
            unique_menu_names.append(menu_name)

        if unique_photos:
            candidates = []

            for menu_name in unique_menu_names:
                for url, image in image_cache.items():
                    score = self._siglip_similarity(menu_name, image)
                    if score >= match_threshold:
                        candidates.append({
                            "menu_name": menu_name,
                            "photo_url": url,
                            "score": float(score),
                        })

            candidates.sort(key=lambda item: item["score"], reverse=True)

            matches = []
            assigned_menu_names = set()
            assigned_photo_urls = set()

            for candidate in candidates:
                menu_name = candidate["menu_name"]
                photo_url = candidate["photo_url"]

                if menu_name in assigned_menu_names or photo_url in assigned_photo_urls:
                    continue

                assigned_menu_names.add(menu_name)
                assigned_photo_urls.add(photo_url)
                matches.append(candidate)

            matches.sort(key=lambda item: unique_menu_names.index(item["menu_name"]))
            return matches

        matches = []

        for menu_name in unique_menu_names:
            best_score = -1.0
            best_url = ""

            for url, image in image_cache.items():
                score = self._siglip_similarity(menu_name, image)
                if score > best_score:
                    best_score = score
                    best_url = url

            if best_url and best_score >= match_threshold:
                matches.append({
                    "menu_name": menu_name,
                    "photo_url": best_url,
                    "score": float(best_score),
                })

        return matches

    def filter_food_photos(self, image_urls, threshold=0.5, return_scores=False):
        """식당 외관/간판/실내 사진을 제외하고 음식 사진으로 보이는 URL만 반환한다."""
        if not image_urls:
            return []

        self._ensure_siglip_model()

        food_labels = [
            "음식 사진",
            "요리 사진",
            "접시에 담긴 메뉴 사진",
            "식탁 위 음식 사진",
        ]
        non_food_labels = [
            "식당 외관 사진",
            "식당 내부 사진",
            "간판 사진",
            "메뉴판 사진",
            "사람 사진",
        ]
        labels = food_labels + non_food_labels

        food_photos = []

        for url in image_urls:
            image = self._load_image_from_url(url)
            if image is None:
                continue

            scores = self._siglip_label_probabilities(labels, image)
            food_score = sum(scores[label] for label in food_labels)
            non_food_score = sum(scores[label] for label in non_food_labels)
            is_food = food_score >= threshold and food_score > non_food_score

            if not is_food:
                continue

            if return_scores:
                food_photos.append({
                    "url": url,
                    "food_score": float(food_score),
                    "non_food_score": float(non_food_score),
                })
            else:
                food_photos.append(url)

        return food_photos

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

    def _siglip_label_probabilities(self, labels, image):
        inputs = self.siglip_processor(
            text=labels,
            images=image,
            padding="max_length",
            return_tensors="pt",
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}

        with torch.no_grad():
            outputs = self.siglip_model(**inputs)

        probabilities = torch.softmax(outputs.logits_per_image.squeeze(0), dim=0)
        return {
            label: float(probability.item())
            for label, probability in zip(labels, probabilities)
        }

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

    def _handle_menu_extraction_error(self, exc):
        if os.getenv("AI_DEBUG") == "1":
            print(f"[MenuAIProcessor] extract_menu_names_from_reviews failed: {exc}", file=sys.stderr)

        return {
            "restaurant_name": "",
            "menus": [],
        }

    def _cosine_similarity(self, vec1, vec2):
        """코사인 유사도 계산."""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        denominator = np.linalg.norm(vec1) * np.linalg.norm(vec2)

        if denominator == 0:
            return 0.0

        return np.dot(vec1, vec2) / denominator
