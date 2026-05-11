import flet as ft
import requests
import os

def main(page: ft.Page):
    # 아이폰 사이즈
    page.window_width = 450
    page.window_height = 800
    page.bgcolor = "#F5F5F7"
    page.padding = 16
    page.scroll = ft.ScrollMode.AUTO

    # --- 상태 관리 변수 ---
    user_location = {"lat": 37.8813, "lng": 127.7298}  # 기본값: 춘천 근처
    radius_km = 2.0
    search_mode = "음식점"
    selected_keywords = set()
    keyword_options = ["달콤한", "매콤한", "새콤한", "바삭한", "부드러운", "구수한"]
    api_base_url = "http://127.0.0.1:8000"
    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")

    def get_google_map_url(lat, lng):
        if google_maps_api_key:
            return (
                "https://www.google.com/maps/embed/v1/view"
                f"?key={google_maps_api_key}&center={lat},{lng}&zoom=16&maptype=roadmap"
            )
        return f"https://maps.google.com/maps?q={lat},{lng}&z=16&output=embed"

    def get_google_static_map_url(lat, lng):
        if not google_maps_api_key:
            return ""
        return (
            "https://maps.googleapis.com/maps/api/staticmap"
            f"?center={lat},{lng}&zoom=16&size=800x500&maptype=roadmap"
            f"&markers=color:red%7C{lat},{lng}&key={google_maps_api_key}"
        )

    # --- API 통신 함수 ---
    def fetch_search_results(lat, lng, radius, query, mode, keywords):
        # 기능 1. 위치 + 검색어 + 검색모드 + 키워드 기반 검색 API 호출
        params = {
            "lat": lat,
            "lng": lng,
            "radius_km": radius,
            "query": query,
            "search_mode": mode,
            "keywords": ",".join(keywords),
        }

        try:
            response = requests.get(
                f"{api_base_url}/api/search",
                params=params,
                timeout=3,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if isinstance(results, list):
                return results
        except Exception:
            # 서버 연동 전/실패 시에도 UI 확인 가능하도록 fallback 유지
            pass

        # 테스트용 fallback 데이터
        return [
            {"menu_id": "M1", "menu_name": "파스타", "price": 12000, "photo_url": "", "core_pros": "양 많음", "core_cons": "느끼함"},
            {"menu_id": "M2", "menu_name": "마라탕", "price": 10000, "photo_url": "", "core_pros": "맵기 조절 가능", "core_cons": "피크 타임 웨이팅"},
            {"menu_id": "M3", "menu_name": "돈까스", "price": 9500, "photo_url": "", "core_pros": "바삭함", "core_cons": "소스가 달다"},
        ]

    def fetch_menu_details(menu_id):
        # 기능 2. 메뉴 상세 정보 API 호출
        try:
            response = requests.get(
                f"{api_base_url}/api/menu/{menu_id}/details",
                timeout=3,
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                details = data.get("details", [])
                if isinstance(details, list):
                    return details
        except Exception:
            pass

        return []

    # --- UI 이벤트 핸들러 ---
    def on_menu_click(e):
        # 메뉴 터치 시 상세 모달 오픈 로직
        menu_id = e.control.data
        details = fetch_menu_details(menu_id)

        if not details:
            details = [
                {
                    "info_id": 101,
                    "content": "고기가 정말 두툼하고 식감이 좋아요.",
                    "info_type": "PROS",
                    "upvotes": 5,
                    "downvotes": 1,
                },
                {
                    "info_id": 102,
                    "content": "소스가 조금 달다는 의견이 있어요.",
                    "info_type": "CONS",
                    "upvotes": 2,
                    "downvotes": 0,
                },
            ]

        review_tiles = []

        for d in details:
            is_pro = d.get("info_type") == "PROS"

            upvote_text = ft.Text(f"👍 {d.get('upvotes', 0)}", size=12)
            downvote_text = ft.Text(f"👎 {d.get('downvotes', 0)}", size=12)

            review_tiles.append(
                ft.Container(
                    padding=12,
                    border_radius=12,
                    bgcolor="#F0F5FF" if is_pro else "#FFF0F0",
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        "장점 리뷰" if is_pro else "단점 리뷰",
                                        weight="bold",
                                        color="blue" if is_pro else "red",
                                    ),
                                ]
                            ),
                            ft.Text(d.get("content", ""), size=14),
                            ft.Row(
                                [
                                    ft.TextButton(
                                        content=upvote_text,
                                        on_click=lambda e, info_id=d["info_id"], up=upvote_text, down=downvote_text:
                                            on_vote_click(info_id, True, up, down)
                                    ),
                                    ft.TextButton(
                                        content=downvote_text,
                                        on_click=lambda e, info_id=d["info_id"], up=upvote_text, down=downvote_text:
                                            on_vote_click(info_id, False, up, down)
                                    ),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=6,
                    ),
                )
            )

        detail_view = ft.Column(
            [
                ft.Text("상세 코어 리뷰", size=20, weight="bold"),
                ft.Text("리뷰가 도움이 되었는지 추천/비추천을 선택할 수 있습니다.", size=12, color="#6B7280"),
                *review_tiles,
            ],
            tight=True,
            spacing=10,
        )

        page.show_bottom_sheet(
            ft.BottomSheet(
                ft.Container(
                    detail_view,
                    bgcolor="white",
                    padding=20,
                    border_radius=ft.border_radius.only(top_left=20, top_right=20),
                )
            )
        )

    def on_vote_click(info_id, is_up, upvote_text=None, downvote_text=None):
        # 추천/비추천 버튼 클릭 시 서버 전송 및 UI 갱신
        payload = {
            "info_id": info_id,
            "is_up": is_up,
        }

        snack_message = "추천이 반영되었습니다!" if is_up else "비추천이 반영되었습니다!"

        try:
            response = requests.post(
                f"{api_base_url}/api/vote",
                json=payload,
                timeout=3,
            )
            response.raise_for_status()

            # 서버 응답에 최신 추천/비추천 수가 있으면 반영
            data = response.json() if response.content else {}

            if upvote_text and "upvotes" in data:
                upvote_text.value = f"👍 {data['upvotes']}"

            if downvote_text and "downvotes" in data:
                downvote_text.value = f"👎 {data['downvotes']}"

        except Exception:
            # 서버 연결 전에도 UI 확인 가능하도록 임시 로컬 증가
            if is_up and upvote_text:
                current = int(upvote_text.value.replace("👍", "").strip())
                upvote_text.value = f"👍 {current + 1}"

            if not is_up and downvote_text:
                current = int(downvote_text.value.replace("👎", "").strip())
                downvote_text.value = f"👎 {current + 1}"

            snack_message = "서버 미연결 상태입니다. 임시로 UI에만 반영했습니다."

        page.snack_bar = ft.SnackBar(ft.Text(snack_message))
        page.snack_bar.open = True
        page.update()

    def update_location_ui():
        location_text.value = f"현재 위치: {user_location['lat']:.4f}, {user_location['lng']:.4f}"
        map_center_text.value = f"지도 중심: {user_location['lat']:.4f}, {user_location['lng']:.4f}"
        if map_webview:
            map_webview.url = get_google_map_url(user_location["lat"], user_location["lng"])
        if map_image:
            map_image.src = get_google_static_map_url(user_location["lat"], user_location["lng"])
        page.update()

    def refresh_search_mode_ui():
        mode_hints = {
            "음식점": "음식점 이름으로 검색",
            "메뉴": "메뉴 이름으로 검색",
            "키워드": "맛/분위기 키워드로 검색",
        }
        for label, button in mode_buttons.items():
            is_active = label == search_mode
            button.bgcolor = "#FFE8CC" if is_active else "#F3F4F6"
            button.border = ft.border.all(1, "#FF8A00" if is_active else "#E5E7EB")
            button.content.color = "#B45309" if is_active else "#4B5563"
            button.content.weight = ft.FontWeight.W_600 if is_active else ft.FontWeight.W_400
        search_bar.hint_text = mode_hints.get(search_mode, "검색어를 입력하세요")
        selected_mode_text.value = f"검색 타입: {search_mode}"

    def refresh_keyword_ui():
        for label, chip in keyword_chips.items():
            is_selected = label in selected_keywords
            chip.bgcolor = "#FFE4E6" if is_selected else "#F3F4F6"
            chip.border = ft.border.all(1, "#FB7185" if is_selected else "#E5E7EB")
            chip.content.controls[0].value = f"{'✓ ' if is_selected else ''}{label}"

        if selected_keywords:
            selected_keywords_text.value = "선택 키워드: " + ", ".join(sorted(selected_keywords))
        else:
            selected_keywords_text.value = "선택 키워드: 없음"

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

    def on_radius_change(e):
        nonlocal radius_km
        radius_km = round(e.control.value, 1)
        radius_value_text.value = f"{radius_km:.1f} km"
        radius_description.value = f"현재 위치 기준 {radius_km:.1f}km 내 메뉴를 검색합니다."
        page.update()

    def on_mode_select(e):
        nonlocal search_mode
        search_mode = e.control.data
        refresh_search_mode_ui()
        page.update()

    def on_keyword_toggle(e):
        keyword = e.control.data
        if keyword in selected_keywords:
            selected_keywords.remove(keyword)
        else:
            selected_keywords.add(keyword)
        refresh_keyword_ui()
        page.update()

    def set_current_location(e):
        # 실제 앱에서는 GPS API 응답값으로 갱신
        user_location["lat"] = 37.5665
        user_location["lng"] = 126.9780
        update_location_ui()
        page.snack_bar = ft.SnackBar(ft.Text("현재 위치를 춘천 시청 기준으로 갱신했습니다."))
        page.snack_bar.open = True
        page.update()

    # 검색 버튼 클릭 시 동작
    def search_action(e):
        search_query = search_bar.value.strip() if search_bar.value else ""
        sorted_keywords = sorted(selected_keywords)
        results = fetch_search_results(
            user_location["lat"],
            user_location["lng"],
            radius_km,
            search_query,
            search_mode,
            sorted_keywords,
        )

        if search_mode == "키워드" and sorted_keywords:
            # 키워드 어미(한/함 등) 차이를 완화하기 위한 간단한 정규화
            normalized_tokens = []
            for keyword in sorted_keywords:
                token = keyword.strip()
                normalized_tokens.append(token)
                if len(token) > 1:
                    normalized_tokens.append(token[:-1])

            filtered_by_keyword = []
            for item in results:
                searchable_text = " ".join([
                    str(item.get("menu_name", "")),
                    str(item.get("core_pros", "")),
                    str(item.get("core_cons", "")),
                ]).lower()
                if any(token.lower() in searchable_text for token in normalized_tokens):
                    filtered_by_keyword.append(item)
            results = filtered_by_keyword

        if search_query:
            query_lower = search_query.lower()
            results = [
                item for item in results
                if query_lower in str(item.get("menu_name", "")).lower()
            ]
        search_summary.value = (
            f"'{search_mode}' 검색 | 키워드 {len(selected_keywords)}개 | "
            f"반경 {radius_km:.1f}km | 결과 {len(results)}건"
        )
        if search_query:
            search_summary.value += f" | 입력어: {search_query}"
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
    location_text = ft.Text("", size=12, color="#374151")
    map_center_text = ft.Text("", size=12, color="#6B7280")
    selected_mode_text = ft.Text("", size=12, color="#6B7280")
    selected_keywords_text = ft.Text("선택 키워드: 없음", size=12, color="#6B7280")
    search_summary = ft.Text("검색 조건을 선택하고 검색 버튼을 눌러주세요.", size=12, color="#6B7280")
    radius_value_text = ft.Text(f"{radius_km:.1f} km", size=20, weight="bold", color="#111827")
    radius_description = ft.Text(f"현재 위치 기준 {radius_km:.1f}km 내 메뉴를 검색합니다.", size=12, color="#6B7280")
    radius_slider = ft.Slider(
        min=0.5,
        max=5.0,
        divisions=9,
        label="반경 {value}km",
        value=radius_km,
        on_change=on_radius_change
    )
    menu_list = ft.ListView(expand=True)
    mode_buttons = {
        "음식점": ft.Container(
            data="음식점",
            on_click=on_mode_select,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=20,
            bgcolor="#F3F4F6",
            border=ft.border.all(1, "#E5E7EB"),
            content=ft.Text("음식점", size=12, color="#4B5563"),
        ),
        "메뉴": ft.Container(
            data="메뉴",
            on_click=on_mode_select,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=20,
            bgcolor="#F3F4F6",
            border=ft.border.all(1, "#E5E7EB"),
            content=ft.Text("메뉴", size=12, color="#4B5563"),
        ),
        "키워드": ft.Container(
            data="키워드",
            on_click=on_mode_select,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=20,
            bgcolor="#F3F4F6",
            border=ft.border.all(1, "#E5E7EB"),
            content=ft.Text("키워드", size=12, color="#4B5563"),
        ),
    }
    keyword_chips = {}
    for keyword in keyword_options:
        keyword_chips[keyword] = ft.Container(
            data=keyword,
            on_click=on_keyword_toggle,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=20,
            bgcolor="#F3F4F6",
            border=ft.border.all(1, "#E5E7EB"),
            content=ft.Row([ft.Text(keyword, size=12, color="#4B5563")], tight=True),
        )

    map_webview = None
    map_image = None
    map_controls = []
    if hasattr(ft, "WebView"):
        map_webview = ft.WebView(
            url=get_google_map_url(user_location["lat"], user_location["lng"]),
            expand=True,
        )
        map_controls.append(map_webview)
    else:
        if google_maps_api_key:
            map_image = ft.Image(
                src=get_google_static_map_url(user_location["lat"], user_location["lng"]),
                fit=ft.ImageFit.COVER,
                expand=True,
            )
            map_controls.append(map_image)
        else:
            map_controls.append(
                ft.Container(
                    expand=True,
                    bgcolor="#C8DEFF",
                    alignment=ft.Alignment(0, 0),
                    content=ft.Column(
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text("WebView 미지원 환경입니다.", color="#1E3A8A"),
                            ft.Text("GOOGLE_MAPS_API_KEY 설정 시 Static Map으로 표시됩니다.", size=12, color="#1E3A8A"),
                            ft.TextButton(
                                "구글 지도 열기",
                                on_click=lambda _: page.launch_url(
                                    f"https://maps.google.com/?q={user_location['lat']},{user_location['lng']}"
                                ),
                            ),
                        ],
                        spacing=4,
                    ),
                )
            )

    map_controls.append(
        ft.Container(
            right=12,
            top=12,
            bgcolor="white",
            border_radius=20,
            padding=10,
            content=ft.Text("📍", size=18),
        )
    )

    map_area = ft.Container(
        height=280,
        border_radius=16,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        bgcolor="#DCEBFF",
        content=ft.Stack(controls=map_controls),
    )

    page.add(
        ft.Column([
            ft.Container(
                padding=12,
                border_radius=12,
                bgcolor="white",
                content=ft.Column([
                    ft.Text("검색 필터", weight="bold"),
                    ft.Row(
                        list(mode_buttons.values()),
                        spacing=8,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    selected_mode_text,
                    ft.Text("키워드 선택", weight="bold"),
                    ft.Row(
                        list(keyword_chips.values()),
                        spacing=8,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    selected_keywords_text,
                ], spacing=8)
            ),
            ft.Row([
                search_bar,
                ft.ElevatedButton("검색", on_click=search_action)
            ]),
            search_summary,
            ft.Container(
                padding=12,
                border_radius=12,
                bgcolor="white",
                content=ft.Column([
                    ft.Row([
                        ft.Text("검색 반경 설정", weight="bold"),
                        radius_value_text
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    radius_slider,
                    radius_description
                ], spacing=6)
            ),
            ft.Container(height=8),
            map_area,
            ft.Row([
                location_text,
                ft.TextButton("내 위치 갱신", on_click=set_current_location)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(),
            menu_list
        ], expand=True)
    )

    refresh_search_mode_ui()
    refresh_keyword_ui()
    update_location_ui()
    page.update()

ft.app(target=main, view=ft.AppView.FLET_APP, port=8550)