import flet as ft
import requests

def main(page: ft.Page):
    # 아이폰 사이즈
    page.window_width = 450   
    page.window_height = 800  
    page.bgcolor = "#F5F5F7" 

    # --- 상태 관리 변수 ---
    current_res_id = None

    # --- API 통신 함수 ---
    def fetch_search_results(lat, lng, radius):
        # 기능 1. 위치 기반 검색 API 호출
        
        # 테스트용 가짜 데이터 (컴포넌트 확인용)
        return [
            {"menu_id": "M1", "menu_name": "파스타", "price": 12000, "photo_url": "", "core_pros": "양 많음", "core_cons": "느끼함"}
        ]

    def fetch_menu_details(menu_id):
        # 기능 2. 메뉴 상세 정보 API 호출
        return [{"info_id": 101, "content": "고기가 정말 두툼해요", "info_type": "PROS", "upvotes": 5}]

    # --- UI 이벤트 핸들러 ---
    def on_menu_click(e):
        # 메뉴 터치 시 상세 모달 오픈 로직
        menu_id = e.control.data # 저장된 menu_id 가져오기
        details = fetch_menu_details(menu_id)
        
        # 공통 상세 모달(BottomSheet) 구성
        detail_view = ft.Column([
            ft.Text("상세 코어 리뷰", size=20, weight="bold"),
            *[ft.ListTile(
                leading=ft.Icon(ft.icons.RECOMMEND if d['info_type'] == 'PROS' else ft.icons.DO_NOT_DISTURB),
                title=ft.Text(d['content']),
                trailing=ft.TextButton(f"👍 {d['upvotes']}", on_click=lambda _: on_vote_click(d['info_id'], True))
            ) for d in details]
        ], tight=True, padding=20)
        
        page.show_bottom_sheet(ft.BottomSheet(ft.Container(detail_view, bgcolor="white", border_radius=ft.border_radius.only(top_left=20, top_right=20))))

    def on_vote_click(info_id, is_up):
        # 추천 버튼 클릭 시 서버 전송 및 UI 갱신
        page.snack_bar = ft.SnackBar(ft.Text("투표가 반영되었습니다!"))
        page.snack_bar.open = True
        page.update()

    # [공통 컴포넌트] 메뉴 카드 생성 함수
    def create_menu_card(m):
        return ft.Card(
            content=ft.Container(
                padding=15,
                on_click=on_menu_click,
                data=m['menu_id'], # 클릭 시 ID 전달용
                content=ft.Column([
                    ft.ListTile(
                        title=ft.Text(m['menu_name'], weight="bold", size=18),
                        subtitle=ft.Text(f"{m['price']}원"),
                    ),
                    ft.Row([
                        ft.Container(content=ft.Text(f"💙 {m['core_pros']}", color="blue"), bgcolor="#F0F5FF", padding=5, border_radius=5),
                        ft.Container(content=ft.Text(f"💔 {m['core_cons']}", color="red"), bgcolor="#FFF0F0", padding=5, border_radius=5),
                    ], spacing=10)
                ])
            )
        )

    # 검색 버튼 클릭 시 동작
    def search_action(e):
        results = fetch_search_results(37.881, 127.730, radius_slider.value)
        menu_list.controls.clear()
        for m in results:
            menu_list.controls.append(create_menu_card(m))
        page.update()

    search_bar = ft.TextField(
        hint_text="음식점 또는 메뉴 검색",
        hint_style=ft.TextStyle(color="#9CA3AF"), 
        expand=True,
        border=ft.InputBorder.NONE,
        bgcolor="transparent",
        content_padding=ft.padding.only(left=10),
    )

    # --- 메인 레이아웃 구성 ---
    radius_slider = ft.Slider(min=0.5, max=5.0, label="반경 {value}km", value=2.0)
    menu_list = ft.ListView(expand=True)

    page.add(
        ft.Column([
            ft.Text("MenuWise", size=30, weight="bold", color="#FF8A00"),
            ft.Row([
                search_bar,
                ft.ElevatedButton("검색", on_click=search_action)
            ]),

            ft.Row([
                ft.Text("검색 반경 설정"),
                ft.Container(content=radius_slider, expand=True)
            ]),
            ft.Divider(),
            menu_list
        ], expand=True)
    )

    page.update()

ft.app(target=main, view=ft.AppView.FLET_APP, port=8550)