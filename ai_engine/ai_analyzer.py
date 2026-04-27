import json
import re
import openai
from sentence_transformers import SentenceTransformer
import numpy as np


class MenuAIProcessor:
    def __init__(self, api_key):
        """LLM + 벡터 모델 초기화"""
        self.api_key = api_key
        self.client = openai.OpenAI(api_key=api_key)

        # SBERT 모델 (키워드 검색용)
        self.vector_model = SentenceTransformer(
            'snunlp/KR-SBERT-V40K-klueNLI-augSTS'
        )

    # --- TODO: 박진우 구현 영역 ---
    def analyze_reviews(self, menu_name, reviews) -> dict:
        """
        [Level 1 & 2 생성 - 개선 버전]

        - 프롬프트 최적화
        - JSON 안정성 강화
        """

        prompt = f"""
        당신은 음식 리뷰 분석 전문가입니다.

        메뉴 '{menu_name}'에 대한 리뷰:
        {reviews}

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

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2  # 일관성 ↑
            )

            raw = response.choices[0].message.content.strip()

            # JSON 정제 강화 (3주차 개선)
            raw = self._extract_json(raw)

            result = json.loads(raw)

        except Exception:
            result = {
                "level_1": {"pros": "", "cons": ""},
                "level_2": []
            }

        return result

    def match_photo(self, menu_name, image_urls) -> str:
        """
        [VLM 기반 확장 구조 - 4주차]

        - 현재: 텍스트 기반 유사도 매칭 (CLIP 대체 구조)
        - 향후: 실제 VLM으로 교체 가능
        """

        if not image_urls:
            return "default_url"

        # 메뉴 이름을 벡터화
        menu_vec = self.vector_model.encode([menu_name])[0]

        best_score = -1
        best_url = image_urls[0]

        for url in image_urls:
            # 현재는 URL 텍스트 기반 비교 (mock)
            img_vec = self.vector_model.encode([url])[0]

            score = self._cosine_similarity(menu_vec, img_vec)

            if score > best_score:
                best_score = score
                best_url = url

        return best_url

    def vectorize_text(self, text_list):
        """
        [벡터화 + 검색 확장]

        - SBERT 기반 임베딩 생성
        - 향후 추천 시스템 활용
        """

        embeddings = self.vector_model.encode(text_list)
        return embeddings.tolist()

    # -------------------------
    # 추가 기능 (3~4주차 구현)
    # -------------------------

    def search_similar(self, query, text_list):
        """
        [유사도 기반 검색 기능 - 4주차]

        - 키워드 기반 추천 기능
        """

        query_vec = self.vector_model.encode([query])[0]
        text_vecs = self.vector_model.encode(text_list)

        scores = []

        for i, vec in enumerate(text_vecs):
            score = self._cosine_similarity(query_vec, vec)
            scores.append((text_list[i], score))

        # 유사도 기준 정렬
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores

    # -------------------------
    # 내부 유틸
    # -------------------------

    def _extract_json(self, text):
        """
        [JSON 안정화 - 3주차 핵심 구현]

        - markdown 제거
        - JSON 블록만 추출
        """

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        text = text.strip()

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group()

        return text

    def _cosine_similarity(self, vec1, vec2):
        """코사인 유사도 계산"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)

        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))