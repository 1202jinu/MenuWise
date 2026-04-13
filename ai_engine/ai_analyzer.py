import openai
from sentence_transformers import SentenceTransformer


class MenuAIAnalyzer:
    def __init__(self, api_key):
        """LLM + 벡터 모델 초기화"""
        self.client = openai.OpenAI(api_key=api_key)
        self.vector_model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')

    def generate_hierarchical_summary(self, menu_name, reviews):
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
                {{ "content": "상세 장점", "type": "PROS" }},
                {{ "content": "상세 단점", "type": "CONS" }}
            ]
        }}
        """

        response = self.client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        return response.choices[0].message.content

    def find_best_menu_photo(self, menu_name, photo_urls):
        """
        [VLM 활용 사진 매칭]
        현재는 간단히 첫 번째 사진 반환 (추후 확장 예정)
        """

        if not photo_urls:
            return "default_url"

        best_photo = photo_urls[0]

        print(f"[AI] '{menu_name}' 대표 사진 선정 완료")
        return best_photo

    def vectorize_text(self, text_list):
        """
        [키워드 검색 최적화]
        문장 벡터화
        """

        embeddings = self.vector_model.encode(text_list)
        return embeddings.tolist()