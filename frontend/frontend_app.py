import flet as ft
import requests

def main(page: ft.Page):
    # --- 상태 관리 변수 ---
    current_res_id = None

    # --- API 통신 함수 ---
    def fetch_search_results(lat, lng, radius):
        # TODO: requests.get("/api/search") 호출
        pass

    def fetch_menu_details(menu_id):
        # TODO: requests.get(f"/api/menu/{menu_id}/details") 호출
        pass

    # --- UI 이벤트 핸들러 ---
    def on_menu_click(e):
        """메뉴 터치 시 상세 모달 오픈 로직"""
        # TODO: fetch_menu_details 실행 후 BottomSheet 띄우기
        pass

    def on_vote_click(info_id, is_up):
        """추천 버튼 클릭 시 서버 전송 및 UI 갱신"""
        pass

    # --- 메인 레이아웃 구성 ---
    page.add(
        ft.Column([
            ft.Text("메뉴와이즈", size=30),
            ft.Slider(min=0.5, max=5.0, label="반경 {value}km"),
            ft.ListView(expand=True) # 여기에 MenuCard들이 추가됨
        ])
    )

ft.app(target=main)