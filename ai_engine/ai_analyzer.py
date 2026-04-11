import json

class MenuAIProcessor:
    def __init__(self, api_key):
        self.api_key = api_key

    # --- TODO: 박진우 구현 영역 ---
    def analyze_reviews(self, menu_name, reviews) -> dict:
        """
        LLM 호출을 통해 아래 구조의 JSON 반환:
        {
          "level_1": {"pros": "...", "cons": "..."},
          "level_2": [{"content": "...", "type": "PROS"}, ...]
        }
        """
        pass

    def match_photo(self, menu_name, image_urls) -> str:
        """VLM으로 가장 적합한 실물 사진 URL 1개 선정"""
        pass