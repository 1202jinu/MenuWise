import json
from ai_analyzer import MenuAIAnalyzer


class MenuAIProcessor:
    def __init__(self, api_key):
        self.api_key = api_key
        self.analyzer = MenuAIAnalyzer(api_key)

    def analyze_reviews(self, menu_name, reviews) -> dict:
        """
        Analyzer를 호출하여 JSON 결과 반환
        """

        raw_result = self.analyzer.generate_hierarchical_summary(menu_name, reviews)

        # JSON 안정 파싱
        try:
            result_json = json.loads(raw_result)
        except Exception:
            result_json = {
                "level_1": {"pros": "", "cons": ""},
                "level_2": []
            }

        return result_json

    def match_photo(self, menu_name, image_urls) -> str:
        """대표 사진 선정"""
        return self.analyzer.find_best_menu_photo(menu_name, image_urls)