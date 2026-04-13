import json
import openai
from sentence_transformers import SentenceTransformer


class MenuAIProcessor:
    def __init__(self, api_key):
        """LLM + 벡터 모델 초기화"""
        self.api_key = api_key
        self.client = openai.OpenAI(api_key=api_key)

        # 한국어 벡터 모델
        self.vector_model = SentenceTransformer(
            'snunlp/KR-SBERT-V40K-klueNLI-augSTS'
        )

    # --- TODO: 박진우 구현 영역 ---
    def analyze_reviews(self, menu_name, reviews) -> dict:
        """
        [Level 1 & 2 생성]
        리뷰를 분석하여 JSON 형태의 요약 생성
        """

        prompt = f"""
        메뉴 '{menu_name}'에 대한 리뷰:
        {reviews}

        반드시 아래 JSON 형식으로만 답변:
        {{
            "level_1": {{
                "pros": "대표 장점 한 줄",
                "cons": "대표 단점 한 줄"
            }},
            "level_2": [
                {{ "content": "상세 내용", "type": "PROS" }},
                {{ "content": "상세 내용", "type": "CONS" }}
            ]
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # 추천 모델
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            raw = response.choices[0].message.content.strip()

            # JSON 정제
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            result = json.loads(raw)

        except Exception:
            # 실패 시 fallback
            result = {
                "level_1": {"pros": "", "cons": ""},
                "level_2": []
            }

        return result

    def match_photo(self, menu_name, image_urls) -> str:
        """
        [VLM 활용 사진 매칭]
        현재는 간단히 첫 번째 사진 반환 (추후 확장 예정)
        """

        if not image_urls:
            return "default_url"

        return image_urls[0]

    def vectorize_text(self, text_list):
        """
        [키워드 검색 최적화]
        문장 벡터화
        """

        embeddings = self.vector_model.encode(text_list)
        return embeddings.tolist()