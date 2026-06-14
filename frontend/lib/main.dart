import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:pointer_interceptor/pointer_interceptor.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:menu_wise/osm_map_canvas.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  runApp(const MenuWiseApp());
}

class MenuWiseApp extends StatelessWidget {
  const MenuWiseApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MenuWise',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: AppColors.background,
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.primary,
          primary: AppColors.primary,
          secondary: AppColors.secondary,
          surface: AppColors.background,
          error: AppColors.destructive,
        ),
        fontFamily: _usesAppleFont ? 'Apple SD Gothic Neo' : null,
      ),
      home: const MenuWiseHomePage(),
    );
  }
}

class MenuWiseHomePage extends StatefulWidget {
  const MenuWiseHomePage({super.key});

  @override
  State<MenuWiseHomePage> createState() => _MenuWiseHomePageState();
}

class _MenuWiseHomePageState extends State<MenuWiseHomePage> {
  final ApiClient _api = ApiClient();
  final TextEditingController _searchController = TextEditingController();
  final Set<String> _selectedKeywords = <String>{};

  static const List<TasteKeyword> _keywords = <TasteKeyword>[
    TasteKeyword('sweet', '달콤', '달콤한', '🍯'),
    TasteKeyword('spicy', '매콤', '매콤한', '🌶️'),
    TasteKeyword('sour', '새콤', '새콤한', '🍋'),
    TasteKeyword('crispy', '바삭', '바삭한', '✨'),
    TasteKeyword('soft', '부드러', '부드러운', '🥚'),
    TasteKeyword('savory', '구수', '구수한', '🍜'),
    TasteKeyword('value', '가성비', '가성비', '💰'),
  ];

  double _userLat = 37.8615;
  double _userLng = 127.7355;
  double _camLat = 37.8615;
  double _camLng = 127.7355;
  int _searchRadiusMeters = 1500;
  SearchMode _searchMode = SearchMode.restaurant;
  bool _showSettings = false;
  bool _isLoading = false;
  bool _isLocating = false;
  bool _sheetOpen = false;
  bool _sheetIsSearch = false;
  String _sheetTitle = '근처 메뉴';
  String? _errorMessage;
  MenuSummary? _selectedMenu;
  List<RestaurantPin> _restaurants = <RestaurantPin>[];
  List<MenuSummary> _sheetMenus = <MenuSummary>[];

  @override
  void initState() {
    super.initState();
    _loadCurrentLocationThenRestaurants();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadCurrentLocationThenRestaurants() async {
    setState(() => _isLocating = true);
    try {
      final position = await _getCurrentPosition();
      if (!mounted) return;
      setState(() {
        _userLat = position.latitude;
        _userLng = position.longitude;
        _camLat = position.latitude;
        _camLng = position.longitude;
      });
    } catch (_) {
      // 위치 거부 시 강원대 기본 좌표 유지
    } finally {
      if (mounted) setState(() => _isLocating = false);
    }
    await _loadRestaurants();
  }

  Future<Position> _getCurrentPosition() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      throw StateError('Location service is disabled');
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
      throw StateError('Location permission is denied');
    }
    return Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
    ).timeout(const Duration(seconds: 8));
  }

  // 지도 핀(식당 목록) 로드. query가 있으면 식당명/카테고리로 거른다.
  Future<void> _loadRestaurants({String query = ''}) async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final restaurants = await _api.fetchRestaurants(
        lat: _userLat,
        lng: _userLng,
        radiusKm: _searchRadiusMeters / 1000,
        query: query,
      );
      if (!mounted) return;
      setState(() {
        _restaurants = restaurants;
        if (query.isNotEmpty && restaurants.isNotEmpty) {
          _camLat = restaurants.first.latitude;
          _camLng = restaurants.first.longitude;
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _restaurants = <RestaurantPin>[];
        _errorMessage = 'FastAPI 서버에 연결할 수 없습니다. ${_api.baseUrl} 상태를 확인해 주세요.';
      });
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  // 검색 버튼/엔터: 모드별 동작
  Future<void> _runSearch() async {
    final query = _searchController.text.trim();

    if (_searchMode == SearchMode.restaurant) {
      setState(() => _sheetOpen = false);
      await _loadRestaurants(query: query);
      return;
    }

    // 키워드 모드: 상단에서 선택한 키워드 + 입력칸에 직접 친 키워드를 함께 사용
    final keywordSet = <String>{..._selectedKeywords};
    if (_searchMode == SearchMode.keyword && query.isNotEmpty) {
      keywordSet.add(query);
    }

    if (_searchMode == SearchMode.keyword && keywordSet.isEmpty) {
      setState(() {
        _sheetMenus = <MenuSummary>[];
        _sheetOpen = false;
        _errorMessage = '검색할 키워드를 입력하거나 상단에서 선택해 주세요.';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final results = await _api.searchMenus(
        lat: _userLat,
        lng: _userLng,
        radiusKm: _searchRadiusMeters / 1000,
        query: _searchMode == SearchMode.menu ? query : '',
        mode: _searchMode,
        keywords: _searchMode == SearchMode.keyword
            ? (keywordSet.toList()..sort())
            : <String>[],
      );
      if (!mounted) return;
      setState(() {
        _sheetMenus = results;
        _sheetIsSearch = true;
        _sheetTitle = _searchMode == SearchMode.menu
            ? (query.isEmpty ? '메뉴 검색' : "'$query' 비교")
            : '키워드 검색 결과';
        _sheetOpen = results.isNotEmpty;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _sheetMenus = <MenuSummary>[];
        _sheetOpen = false;
        _errorMessage = 'FastAPI 서버에 연결할 수 없습니다. ${_api.baseUrl} 상태를 확인해 주세요.';
      });
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _setSearchMode(SearchMode mode) {
    setState(() => _searchMode = mode);
  }

  void _toggleKeyword(TasteKeyword keyword) {
    setState(() {
      _searchMode = SearchMode.keyword;
      if (!_selectedKeywords.add(keyword.label)) {
        _selectedKeywords.remove(keyword.label);
      }
    });
    _runSearch();
  }

  // 식당 핀 탭 → 그 식당의 메뉴를 시트에 표시하고 지도를 식당으로 이동
  Future<void> _openRestaurant({
    required String resId,
    required String name,
    required double lat,
    required double lng,
  }) async {
    setState(() {
      _camLat = lat;
      _camLng = lng;
      _isLoading = true;
    });
    try {
      final menus = await _api.fetchRestaurantMenus(resId, lat: _userLat, lng: _userLng);
      if (!mounted) return;
      setState(() {
        _sheetMenus = menus;
        _sheetIsSearch = false;
        _sheetTitle = name;
        _sheetOpen = true;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _errorMessage = '식당 메뉴를 불러오지 못했습니다.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  // 시트의 메뉴 탭: 검색결과면 식당으로 이동(#6), 식당메뉴면 상세로(#1)
  void _onMenuTap(MenuSummary menu) {
    if (_sheetIsSearch) {
      _openRestaurant(
        resId: menu.resId,
        name: menu.restaurantName.isEmpty ? menu.menuName : menu.restaurantName,
        lat: menu.latitude,
        lng: menu.longitude,
      );
    } else {
      setState(() => _selectedMenu = menu);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: <Widget>[
            Column(
              children: <Widget>[
                FigmaSearchBar(
                  controller: _searchController,
                  searchRadiusMeters: _searchRadiusMeters,
                  showSettings: _showSettings,
                  isLoading: _isLoading,
                  searchMode: _searchMode,
                  onModeChange: _setSearchMode,
                  onSearch: _runSearch,
                  onToggleSettings: () => setState(() => _showSettings = !_showSettings),
                  onRadiusChange: (radius) => setState(() => _searchRadiusMeters = radius),
                  onRadiusChangeEnd: (_) => _loadRestaurants(),
                ),
                KeywordBanner(
                  keywords: _keywords,
                  selectedKeywords: _selectedKeywords,
                  onToggle: _toggleKeyword,
                ),
                Expanded(
                  child: MapView(
                    restaurants: _restaurants,
                    cameraLat: _camLat,
                    cameraLng: _camLng,
                    userLat: _userLat,
                    userLng: _userLng,
                    radiusMeters: _searchRadiusMeters,
                    isLoading: _isLoading || _isLocating,
                    errorMessage: _errorMessage,
                    onRestaurantTap: (pin) => _openRestaurant(
                      resId: pin.resId,
                      name: pin.name,
                      lat: pin.latitude,
                      lng: pin.longitude,
                    ),
                    onLocate: _loadCurrentLocationThenRestaurants,
                    onRetry: _loadRestaurants,
                  ),
                ),
              ],
            ),
            if (_sheetOpen)
              PointerInterceptor(
                child: RestaurantSheet(
                  title: _sheetTitle,
                  menus: _sheetMenus,
                  radiusMeters: _searchRadiusMeters,
                  onClose: () => setState(() => _sheetOpen = false),
                  onMenuSelect: _onMenuTap,
                ),
              ),
            if (_selectedMenu != null)
              MenuDetailPage(
                menu: _selectedMenu!,
                api: _api,
                onClose: () => setState(() => _selectedMenu = null),
              ),
          ],
        ),
      ),
    );
  }
}

class _SearchModeSelector extends StatelessWidget {
  const _SearchModeSelector({required this.mode, required this.onChange});

  final SearchMode mode;
  final ValueChanged<SearchMode> onChange;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.secondary,
        borderRadius: BorderRadius.circular(8),
      ),
      padding: const EdgeInsets.all(3),
      child: Row(
        children: SearchMode.values.map((m) {
          final selected = m == mode;
          return Expanded(
            child: GestureDetector(
              onTap: () => onChange(m),
              child: Container(
                height: 34,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: selected ? AppColors.background : Colors.transparent,
                  borderRadius: BorderRadius.circular(6),
                  boxShadow: selected
                      ? const <BoxShadow>[
                          BoxShadow(color: Color(0x14000000), blurRadius: 6, offset: Offset(0, 2)),
                        ]
                      : null,
                ),
                child: Text(
                  m.label,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: selected ? FontWeight.w800 : FontWeight.w500,
                    color: selected ? AppColors.primary : AppColors.mutedForeground,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class FigmaSearchBar extends StatelessWidget {
  const FigmaSearchBar({
    super.key,
    required this.controller,
    required this.searchRadiusMeters,
    required this.showSettings,
    required this.isLoading,
    required this.searchMode,
    required this.onModeChange,
    required this.onSearch,
    required this.onToggleSettings,
    required this.onRadiusChange,
    required this.onRadiusChangeEnd,
  });

  final TextEditingController controller;
  final int searchRadiusMeters;
  final bool showSettings;
  final bool isLoading;
  final SearchMode searchMode;
  final ValueChanged<SearchMode> onModeChange;
  final VoidCallback onSearch;
  final VoidCallback onToggleSettings;
  final ValueChanged<int> onRadiusChange;
  final ValueChanged<int> onRadiusChangeEnd;

  String get _hint {
    switch (searchMode) {
      case SearchMode.restaurant:
        return '음식점 이름 검색';
      case SearchMode.menu:
        return '메뉴 이름 검색 (예: 국수)';
      case SearchMode.keyword:
        return '키워드로 검색 (예: 매콤)';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.background,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: <Widget>[
            _SearchModeSelector(mode: searchMode, onChange: onModeChange),
            const SizedBox(height: 12),
            Row(
              children: <Widget>[
                Expanded(
                  child: Container(
                    decoration: BoxDecoration(
                      color: AppColors.inputBackground,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: 14),
                    child: TextField(
                      controller: controller,
                      textInputAction: TextInputAction.search,
                      onSubmitted: (_) => onSearch(),
                      decoration: InputDecoration(
                        icon: const Icon(Icons.search, color: AppColors.mutedForeground),
                        hintText: _hint,
                        border: InputBorder.none,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Material(
                  color: AppColors.inputBackground,
                  borderRadius: BorderRadius.circular(8),
                  child: IconButton(
                    tooltip: '검색 설정',
                    onPressed: onToggleSettings,
                    icon: const Icon(Icons.tune),
                  ),
                ),
                const SizedBox(width: 8),
                Material(
                  color: AppColors.primary,
                  borderRadius: BorderRadius.circular(8),
                  child: IconButton(
                    tooltip: '검색',
                    onPressed: isLoading ? null : onSearch,
                    icon: isLoading
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.arrow_forward, color: Colors.white),
                  ),
                ),
              ],
            ),
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 180),
              child: showSettings
                  ? Container(
                      key: const ValueKey<String>('settings'),
                      margin: const EdgeInsets.only(top: 14),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppColors.secondary,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Column(
                        children: <Widget>[
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: <Widget>[
                              const Text('검색 범위', style: TextStyle(fontWeight: FontWeight.w700)),
                              Text(
                                _radiusLabel(searchRadiusMeters),
                                style: const TextStyle(color: AppColors.mutedForeground),
                              ),
                            ],
                          ),
                          Slider(
                            min: 100,
                            max: 3000,
                            divisions: 29,
                            value: searchRadiusMeters.toDouble(),
                            label: _radiusLabel(searchRadiusMeters),
                            onChanged: (value) => onRadiusChange(value.round()),
                            onChangeEnd: (value) => onRadiusChangeEnd(value.round()),
                          ),
                          const Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: <Widget>[
                              Text('100m', style: TextStyle(fontSize: 12, color: AppColors.mutedForeground)),
                              Text('3km', style: TextStyle(fontSize: 12, color: AppColors.mutedForeground)),
                            ],
                          ),
                        ],
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
          ],
        ),
      ),
    );
  }
}

class KeywordBanner extends StatelessWidget {
  const KeywordBanner({
    super.key,
    required this.keywords,
    required this.selectedKeywords,
    required this.onToggle,
  });

  final List<TasteKeyword> keywords;
  final Set<String> selectedKeywords;
  final ValueChanged<TasteKeyword> onToggle;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 78,
      decoration: const BoxDecoration(
        color: AppColors.background,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
        scrollDirection: Axis.horizontal,
        itemBuilder: (context, index) {
          final keyword = keywords[index];
          final selected = selectedKeywords.contains(keyword.label);
          return KeywordChip(
            keyword: keyword,
            selected: selected,
            onTap: () => onToggle(keyword),
          );
        },
        separatorBuilder: (context, index) => const SizedBox(width: 8),
        itemCount: keywords.length,
      ),
    );
  }
}

class KeywordChip extends StatelessWidget {
  const KeywordChip({
    super.key,
    required this.keyword,
    required this.selected,
    required this.onTap,
  });

  final TasteKeyword keyword;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: keyword.display,
      child: Material(
        color: selected ? AppColors.accent : AppColors.secondary,
        borderRadius: BorderRadius.circular(999),
        child: InkWell(
          borderRadius: BorderRadius.circular(999),
          onTap: onTap,
          child: Container(
            height: 42,
            constraints: const BoxConstraints(minWidth: 92),
            padding: const EdgeInsets.symmetric(horizontal: 16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(999),
              border: Border.all(
                color: selected ? AppColors.primary : Colors.transparent,
                width: 1.2,
              ),
            ),
            alignment: Alignment.center,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: <Widget>[
                Text(
                  keyword.emoji,
                  textAlign: TextAlign.center,
                  strutStyle: const StrutStyle(
                    fontSize: 16,
                    height: 1,
                    forceStrutHeight: true,
                  ),
                  style: const TextStyle(fontSize: 16, height: 1),
                ),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    keyword.display,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    strutStyle: const StrutStyle(
                      fontSize: 14,
                      height: 1.1,
                      forceStrutHeight: true,
                    ),
                    style: const TextStyle(
                      fontSize: 14,
                      height: 1.1,
                      color: AppColors.foreground,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class MapView extends StatelessWidget {
  const MapView({
    super.key,
    required this.restaurants,
    required this.cameraLat,
    required this.cameraLng,
    required this.userLat,
    required this.userLng,
    required this.radiusMeters,
    required this.isLoading,
    required this.errorMessage,
    required this.onRestaurantTap,
    required this.onLocate,
    required this.onRetry,
  });

  final List<RestaurantPin> restaurants;
  final double cameraLat;
  final double cameraLng;
  final double userLat;
  final double userLng;
  final int radiusMeters;
  final bool isLoading;
  final String? errorMessage;
  final ValueChanged<RestaurantPin> onRestaurantTap;
  final VoidCallback onLocate;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final mapMarkers = restaurants
        .where((r) => r.latitude != 0 && r.longitude != 0)
        .map(
          (r) => MapMarker(
            id: r.resId,
            title: r.name,
            latitude: r.latitude,
            longitude: r.longitude,
            onTap: () => onRestaurantTap(r),
          ),
        )
        .toList();

    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        OsmMapCanvas(
          cameraLat: cameraLat,
          cameraLng: cameraLng,
          userLat: userLat,
          userLng: userLng,
          radiusMeters: radiusMeters,
          markers: mapMarkers,
        ),
        if (isLoading)
          const Center(child: CircularProgressIndicator())
        else if (restaurants.isEmpty)
          Center(
            child: PointerInterceptor(
              child: MapNotice(
                icon: errorMessage == null ? Icons.nearby_error_outlined : Icons.cloud_off_outlined,
                title: errorMessage == null ? '근처에 식당이 없습니다' : '서버 연결이 필요합니다',
                message: errorMessage ?? '검색 범위를 넓혀 다시 시도해 보세요.',
                onRetry: onRetry,
              ),
            ),
          ),
        Positioned(
          left: 16,
          bottom: 16,
          child: PointerInterceptor(
            child: Material(
              color: AppColors.background,
              borderRadius: BorderRadius.circular(8),
              elevation: 6,
              shadowColor: const Color(0x26000000),
              child: IconButton(
                tooltip: '현재 위치로 이동',
                onPressed: isLoading ? null : onLocate,
                icon: const Icon(Icons.my_location, color: AppColors.foreground),
              ),
            ),
          ),
        ),
        Positioned(
          right: 16,
          bottom: 16,
          child: PointerInterceptor(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: AppColors.background,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.border),
                boxShadow: const <BoxShadow>[
                  BoxShadow(color: Color(0x1A000000), blurRadius: 14, offset: Offset(0, 6)),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: <Widget>[
                  const Text('현재 위치 기준', style: TextStyle(fontSize: 12, color: AppColors.mutedForeground)),
                  Text('${_radiusLabel(radiusMeters)} 이내 식당 ${restaurants.length}곳'),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class RestaurantSheet extends StatelessWidget {
  const RestaurantSheet({
    super.key,
    required this.title,
    required this.menus,
    required this.radiusMeters,
    required this.onClose,
    required this.onMenuSelect,
  });

  final String title;
  final List<MenuSummary> menus;
  final int radiusMeters;
  final VoidCallback onClose;
  final ValueChanged<MenuSummary> onMenuSelect;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.bottomCenter,
      child: Container(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.75),
        decoration: const BoxDecoration(
          color: AppColors.background,
          borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
          boxShadow: <BoxShadow>[
            BoxShadow(color: Color(0x2A000000), blurRadius: 24, offset: Offset(0, -8)),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 12, 12),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800),
                        ),
                        Text(
                          '메뉴 ${menus.length}개',
                          style: const TextStyle(color: AppColors.mutedForeground),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: '닫기',
                    onPressed: onClose,
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: AppColors.border),
            Flexible(
              child: ListView.separated(
                shrinkWrap: true,
                itemBuilder: (context, index) {
                  final menu = menus[index];
                  return MenuListTile(menu: menu, onTap: () => onMenuSelect(menu));
                },
                separatorBuilder: (context, index) => const Divider(height: 1, color: AppColors.border),
                itemCount: menus.length,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class MenuListTile extends StatelessWidget {
  const MenuListTile({super.key, required this.menu, required this.onTap});

  final MenuSummary menu;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              MenuImage(url: menu.photoUrl, size: 96),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Expanded(
                          child: Text(
                            menu.menuName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(menu.priceLabel, style: const TextStyle(fontWeight: FontWeight.w700)),
                      ],
                    ),
                    if (menu.restaurantName.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          menu.restaurantName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 12, color: AppColors.mutedForeground),
                        ),
                      ),
                    const SizedBox(height: 10),
                    ReviewLine(icon: Icons.thumb_up_alt_outlined, color: AppColors.primary, text: menu.corePros),
                    const SizedBox(height: 8),
                    ReviewLine(icon: Icons.thumb_down_alt_outlined, color: AppColors.destructive, text: menu.coreCons),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class MenuDetailPage extends StatefulWidget {
  const MenuDetailPage({
    super.key,
    required this.menu,
    required this.api,
    required this.onClose,
  });

  final MenuSummary menu;
  final ApiClient api;
  final VoidCallback onClose;

  @override
  State<MenuDetailPage> createState() => _MenuDetailPageState();
}

class _MenuDetailPageState extends State<MenuDetailPage> {
  List<CoreInfo> _items = <CoreInfo>[];
  bool _loading = true;
  bool _hasError = false;
  DetailTab _activeTab = DetailTab.positive;

  @override
  void initState() {
    super.initState();
    _loadDetails();
  }

  // 상세를 불러온 뒤, 이 기기에서 이미 누른 추천/비추천 상태를 복원한다.
  Future<void> _loadDetails() async {
    try {
      final details = await widget.api.fetchMenuDetails(widget.menu.menuId);
      for (final info in details) {
        info.userVote = await VoteStore.get(info.infoId);
      }
      _sortByNetVotes(details);
      if (!mounted) return;
      setState(() {
        _items = details;
        _loading = false;
      });
      _syncRepresentative();
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _hasError = true;
        _loading = false;
      });
    }
  }

  // 서버 대표 장단점과 동일한 기준: (추천-비추천) 내림차순, level 오름차순, info_id 오름차순.
  void _sortByNetVotes(List<CoreInfo> list) {
    list.sort((a, b) {
      final netA = a.upvotes - a.downvotes;
      final netB = b.upvotes - b.downvotes;
      if (netA != netB) return netB.compareTo(netA);
      if (a.level != b.level) return a.level.compareTo(b.level);
      return a.infoId.compareTo(b.infoId);
    });
  }

  // 정렬된 목록의 맨 위 PROS/CONS를 대표로 삼아 메뉴 요약(목록 미리보기)에 즉시 반영한다.
  void _syncRepresentative() {
    String pros = '';
    String cons = '';
    for (final info in _items) {
      if (info.infoType == 'PROS' && pros.isEmpty) pros = info.content;
      if (info.infoType == 'CONS' && cons.isEmpty) cons = info.content;
      if (pros.isNotEmpty && cons.isNotEmpty) break;
    }
    widget.menu.corePros = pros;
    widget.menu.coreCons = cons;
  }

  void _applyVoteCounts(CoreInfo info, String from, String to) {
    if (from == 'up') {
      info.upvotes -= 1;
    } else if (from == 'down') {
      info.downvotes -= 1;
    }
    if (to == 'up') {
      info.upvotes += 1;
    } else if (to == 'down') {
      info.downvotes += 1;
    }
    info.userVote = to;
  }

  Future<void> _vote(CoreInfo info, String target) async {
    final previous = info.userVote;
    final next = previous == target ? 'none' : target; // 같은 버튼 두 번 → 취소

    // 낙관적 업데이트: 표 반영 → 재정렬 → 대표 갱신을 즉시 화면에 적용한다.
    setState(() {
      _applyVoteCounts(info, previous, next);
      _sortByNetVotes(_items);
    });
    _syncRepresentative();

    try {
      await widget.api.vote(infoId: info.infoId, vote: next, previous: previous);
      await VoteStore.set(info.infoId, next); // 기기에 영속 저장 → 재방문 시 재투표 방지
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _applyVoteCounts(info, next, previous); // 실패 시 롤백
        _sortByNetVotes(_items);
      });
      _syncRepresentative();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('투표를 저장하지 못했습니다. 서버 상태를 확인해 주세요.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.background,
      child: Column(
        children: <Widget>[
          Container(
            decoration: const BoxDecoration(
              color: AppColors.background,
              border: Border(bottom: BorderSide(color: AppColors.border)),
            ),
            padding: const EdgeInsets.fromLTRB(8, 10, 14, 10),
            child: Row(
              children: <Widget>[
                IconButton(
                  tooltip: '뒤로',
                  onPressed: widget.onClose,
                  icon: const Icon(Icons.arrow_back),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        widget.menu.menuName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                      ),
                      const Text('근처 추천 메뉴', style: TextStyle(color: AppColors.mutedForeground)),
                    ],
                  ),
                ),
                Text(widget.menu.priceLabel, style: const TextStyle(fontWeight: FontWeight.w800)),
              ],
            ),
          ),
          MenuImage(url: widget.menu.photoUrl, width: double.infinity, height: 260),
          Row(
            children: <Widget>[
              DetailTabButton(
                label: '장점',
                selected: _activeTab == DetailTab.positive,
                onTap: () => setState(() => _activeTab = DetailTab.positive),
              ),
              DetailTabButton(
                label: '단점',
                selected: _activeTab == DetailTab.negative,
                onTap: () => setState(() => _activeTab = DetailTab.negative),
              ),
            ],
          ),
          Expanded(child: _buildDetailBody()),
        ],
      ),
    );
  }

  Widget _buildDetailBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_hasError) {
      return const Center(child: Text('상세 리뷰를 불러오지 못했습니다.'));
    }

    final details = _items
        .where((item) => _activeTab == DetailTab.positive ? item.infoType == 'PROS' : item.infoType == 'CONS')
        .toList();

    if (details.isEmpty) {
      return Center(
        child: Text(
          _activeTab == DetailTab.negative ? '단점에 대한 리뷰가 없습니다.' : '장점에 대한 리뷰가 없습니다.',
          style: const TextStyle(color: AppColors.mutedForeground),
        ),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemBuilder: (context, index) {
        final info = details[index];
        return ReviewCard(
          key: ValueKey<int>(info.infoId),
          info: info,
          api: widget.api,
          onLike: () => _vote(info, 'up'),
          onDislike: () => _vote(info, 'down'),
        );
      },
      separatorBuilder: (context, index) => const SizedBox(height: 14),
      itemCount: details.length,
    );
  }
}

class ReviewCard extends StatefulWidget {
  const ReviewCard({
    super.key,
    required this.info,
    required this.api,
    required this.onLike,
    required this.onDislike,
  });

  final CoreInfo info;
  final ApiClient api;
  final VoidCallback onLike;
  final VoidCallback onDislike;

  @override
  State<ReviewCard> createState() => _ReviewCardState();
}

class _ReviewCardState extends State<ReviewCard> {
  final TextEditingController _commentController = TextEditingController();
  final TextEditingController _editController = TextEditingController();
  bool _expanded = false;
  bool _loading = false;
  bool _submitting = false;
  String _token = '';
  int? _editingId; // 현재 인라인 수정 중인 댓글 id (없으면 null)
  bool _savingEdit = false;
  List<MenuComment> _comments = <MenuComment>[];

  @override
  void initState() {
    super.initState();
    CommentIdentity.token().then((value) {
      if (mounted) setState(() => _token = value);
    });
  }

  @override
  void dispose() {
    _commentController.dispose();
    _editController.dispose();
    super.dispose();
  }

  Future<void> _toggleComments() async {
    setState(() => _expanded = !_expanded);
    if (_expanded) {
      await _loadComments();
    }
  }

  Future<void> _loadComments() async {
    setState(() => _loading = true);
    try {
      if (_token.isEmpty) {
        _token = await CommentIdentity.token();
      }
      final comments = await widget.api.fetchComments(widget.info.infoId, token: _token);
      if (!mounted) return;
      setState(() {
        _comments = comments;
        widget.info.commentCount = comments.length;
      });
    } catch (_) {
      // 조회 실패 시 목록은 그대로 둔다.
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submitComment() async {
    final text = _commentController.text.trim();
    if (text.isEmpty || _submitting) return;

    setState(() => _submitting = true);
    try {
      if (_token.isEmpty) {
        _token = await CommentIdentity.token();
      }
      final created = await widget.api.addComment(widget.info.infoId, text, token: _token);
      if (!mounted) return;
      setState(() {
        _comments = <MenuComment>[..._comments, created];
        widget.info.commentCount = _comments.length;
        _commentController.clear();
      });
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('댓글을 저장하지 못했습니다. 서버 상태를 확인해 주세요.')),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  void _startEdit(MenuComment comment) {
    setState(() {
      _editingId = comment.commentId;
      _editController.text = comment.content;
    });
  }

  void _cancelEdit() {
    setState(() => _editingId = null);
  }

  Future<void> _saveEdit(MenuComment comment) async {
    final text = _editController.text.trim();
    if (text.isEmpty || _savingEdit) return;

    setState(() => _savingEdit = true);
    try {
      final updated = await widget.api.updateComment(comment.commentId, text, _token);
      if (!mounted) return;
      setState(() {
        _comments = _comments
            .map((c) => c.commentId == comment.commentId ? c.copyWith(content: updated.content) : c)
            .toList();
        _editingId = null;
      });
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('댓글을 수정하지 못했습니다. 서버 상태를 확인해 주세요.')),
      );
    } finally {
      if (mounted) setState(() => _savingEdit = false);
    }
  }

  Future<void> _deleteComment(MenuComment comment) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('댓글 삭제'),
        content: const Text('이 댓글을 삭제할까요?'),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('취소')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('삭제', style: TextStyle(color: AppColors.destructive)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await widget.api.deleteComment(comment.commentId, _token);
      if (!mounted) return;
      setState(() {
        _comments = _comments.where((c) => c.commentId != comment.commentId).toList();
        widget.info.commentCount = _comments.length;
        if (_editingId == comment.commentId) _editingId = null;
      });
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('댓글을 삭제하지 못했습니다. 서버 상태를 확인해 주세요.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final info = widget.info;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.secondary,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(info.content, style: const TextStyle(height: 1.45)),
          const SizedBox(height: 14),
          Row(
            children: <Widget>[
              CountButton(
                icon: info.userVote == 'up' ? Icons.thumb_up_alt : Icons.thumb_up_alt_outlined,
                count: info.upvotes,
                selected: info.userVote == 'up',
                selectedColor: AppColors.primary,
                onTap: widget.onLike,
              ),
              const SizedBox(width: 10),
              CountButton(
                icon: info.userVote == 'down' ? Icons.thumb_down_alt : Icons.thumb_down_alt_outlined,
                count: info.downvotes,
                selected: info.userVote == 'down',
                selectedColor: AppColors.destructive,
                onTap: widget.onDislike,
              ),
              const SizedBox(width: 10),
              CountButton(
                icon: _expanded ? Icons.mode_comment : Icons.mode_comment_outlined,
                count: info.commentCount,
                selected: _expanded,
                selectedColor: AppColors.foreground,
                onTap: _toggleComments,
              ),
            ],
          ),
          if (_expanded) _buildCommentSection(),
        ],
      ),
    );
  }

  Widget _buildCommentSection() {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Divider(height: 1, color: AppColors.border),
          const SizedBox(height: 10),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2)),
            )
          else if (_comments.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 6),
              child: Text(
                '아직 댓글이 없습니다. 첫 댓글을 남겨보세요.',
                style: TextStyle(fontSize: 12, color: AppColors.mutedForeground),
              ),
            )
          else
            ..._comments.map(_buildCommentTile),
          const SizedBox(height: 4),
          Row(
            children: <Widget>[
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    color: AppColors.background,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: AppColors.border),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: TextField(
                    controller: _commentController,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _submitComment(),
                    decoration: const InputDecoration(
                      hintText: '댓글 남기기 (추가 정보·정정 등)',
                      border: InputBorder.none,
                      isCollapsed: true,
                      contentPadding: EdgeInsets.symmetric(vertical: 12),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Material(
                color: AppColors.primary,
                borderRadius: BorderRadius.circular(8),
                child: IconButton(
                  tooltip: '댓글 등록',
                  onPressed: _submitting ? null : _submitComment,
                  icon: _submitting
                      ? const SizedBox.square(
                          dimension: 16,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : const Icon(Icons.send, size: 18, color: Colors.white),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildCommentTile(MenuComment comment) {
    final editing = _editingId == comment.commentId;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: AppColors.background,
          borderRadius: BorderRadius.circular(8),
        ),
        child: editing ? _buildCommentEditor(comment) : _buildCommentContent(comment),
      ),
    );
  }

  Widget _buildCommentContent(MenuComment comment) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Expanded(
          child: Text(comment.content, style: const TextStyle(fontSize: 13, height: 1.35)),
        ),
        if (comment.isMine) ...<Widget>[
          const SizedBox(width: 6),
          _CommentAction(
            icon: Icons.edit_outlined,
            tooltip: '수정',
            onTap: () => _startEdit(comment),
          ),
          _CommentAction(
            icon: Icons.delete_outline,
            tooltip: '삭제',
            color: AppColors.destructive,
            onTap: () => _deleteComment(comment),
          ),
        ],
      ],
    );
  }

  Widget _buildCommentEditor(MenuComment comment) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: <Widget>[
        TextField(
          controller: _editController,
          autofocus: true,
          textInputAction: TextInputAction.send,
          onSubmitted: (_) => _saveEdit(comment),
          style: const TextStyle(fontSize: 13, height: 1.35),
          decoration: const InputDecoration(
            isCollapsed: true,
            border: InputBorder.none,
            contentPadding: EdgeInsets.symmetric(vertical: 4),
          ),
        ),
        const SizedBox(height: 4),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextButton(
              onPressed: _savingEdit ? null : _cancelEdit,
              style: TextButton.styleFrom(
                minimumSize: const Size(0, 32),
                padding: const EdgeInsets.symmetric(horizontal: 10),
              ),
              child: const Text('취소', style: TextStyle(fontSize: 12, color: AppColors.mutedForeground)),
            ),
            TextButton(
              onPressed: _savingEdit ? null : () => _saveEdit(comment),
              style: TextButton.styleFrom(
                minimumSize: const Size(0, 32),
                padding: const EdgeInsets.symmetric(horizontal: 10),
              ),
              child: _savingEdit
                  ? const SizedBox.square(dimension: 14, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('저장', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.primary)),
            ),
          ],
        ),
      ],
    );
  }
}

class _CommentAction extends StatelessWidget {
  const _CommentAction({
    required this.icon,
    required this.tooltip,
    required this.onTap,
    this.color = AppColors.mutedForeground,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Icon(icon, size: 16, color: color),
        ),
      ),
    );
  }
}

class CountButton extends StatelessWidget {
  const CountButton({
    super.key,
    required this.icon,
    required this.count,
    required this.onTap,
    this.selected = false,
    this.selectedColor = AppColors.primary,
  });

  final IconData icon;
  final int count;
  final VoidCallback onTap;
  final bool selected;
  final Color selectedColor;

  @override
  Widget build(BuildContext context) {
    final color = selected ? selectedColor : AppColors.foreground;
    return Material(
      color: selected ? selectedColor.withValues(alpha: 0.12) : AppColors.background,
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icon, size: 17, color: color),
              const SizedBox(width: 6),
              Text(
                '$count',
                style: TextStyle(
                  color: color,
                  fontWeight: selected ? FontWeight.w800 : FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class DetailTabButton extends StatelessWidget {
  const DetailTabButton({super.key, required this.label, required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Container(
          height: 48,
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(
                color: selected ? AppColors.primary : AppColors.border,
                width: selected ? 2 : 1,
              ),
            ),
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              color: selected ? AppColors.foreground : AppColors.mutedForeground,
              fontWeight: selected ? FontWeight.w800 : FontWeight.w500,
            ),
          ),
        ),
      ),
    );
  }
}

class MenuImage extends StatelessWidget {
  const MenuImage({super.key, required this.url, this.size, this.width, this.height});

  final String url;
  final double? size;
  final double? width;
  final double? height;

  @override
  Widget build(BuildContext context) {
    final imageWidth = width ?? size ?? 96;
    final imageHeight = height ?? size ?? 96;
    return Container(
      width: imageWidth,
      height: imageHeight,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: AppColors.secondary,
        borderRadius: BorderRadius.circular(width == double.infinity ? 0 : 8),
      ),
      child: url.isEmpty
          ? const Center(child: Icon(Icons.restaurant, size: 34, color: AppColors.mutedForeground))
          : Image.network(
              url,
              fit: BoxFit.cover,
              errorBuilder: (context, error, stackTrace) {
                return const Center(child: Icon(Icons.restaurant, size: 34, color: AppColors.mutedForeground));
              },
            ),
    );
  }
}

class ReviewLine extends StatelessWidget {
  const ReviewLine({super.key, required this.icon, required this.color, required this.text});

  final IconData icon;
  final Color color;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(icon, size: 17, color: color),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            text.isEmpty ? '관련 리뷰 없음' : text,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 12, color: AppColors.mutedForeground, height: 1.3),
          ),
        ),
      ],
    );
  }
}

class MapNotice extends StatelessWidget {
  const MapNotice({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
    required this.onRetry,
  });

  final IconData icon;
  final String title;
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 280,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
        boxShadow: const <BoxShadow>[
          BoxShadow(color: Color(0x18000000), blurRadius: 18, offset: Offset(0, 8)),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 42, color: AppColors.mutedForeground),
          const SizedBox(height: 10),
          Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Text(message, textAlign: TextAlign.center, style: const TextStyle(color: AppColors.mutedForeground)),
          const SizedBox(height: 14),
          FilledButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('다시 검색')),
        ],
      ),
    );
  }
}

class FigmaMapPainter extends CustomPainter {
  const FigmaMapPainter();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = AppColors.muted);

    final gridPaint = Paint()
      ..color = const Color(0x11000000)
      ..strokeWidth = 0.8;

    for (double x = 0; x <= size.width; x += 32) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (double y = 0; y <= size.height; y += 32) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    final roadPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 5
      ..color = const Color(0x24000000);

    final path1 = Path()
      ..moveTo(size.width * 0.18, size.height * 0.30)
      ..quadraticBezierTo(size.width * 0.42, size.height * 0.20, size.width * 0.65, size.height * 0.36);
    final path2 = Path()
      ..moveTo(size.width * 0.26, size.height * 0.52)
      ..quadraticBezierTo(size.width * 0.52, size.height * 0.45, size.width * 0.76, size.height * 0.57);
    final path3 = Path()
      ..moveTo(size.width * 0.21, size.height * 0.72)
      ..quadraticBezierTo(size.width * 0.48, size.height * 0.64, size.width * 0.72, size.height * 0.76);

    canvas.drawPath(path1, roadPaint);
    canvas.drawPath(path2, roadPaint);
    canvas.drawPath(path3, roadPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

enum DetailTab { positive, negative }

enum SearchMode {
  restaurant('음식점'),
  menu('메뉴'),
  keyword('키워드');

  const SearchMode(this.label);

  final String label;
}

class TasteKeyword {
  const TasteKeyword(this.id, this.label, this.display, this.emoji);

  final String id;
  final String label; // 실제 검색/매칭에 쓰는 어간 (예: 매콤)
  final String display; // 배너에 보이는 글씨 (예: 매콤한)
  final String emoji;
}

class AppColors {
  static const Color background = Color(0xFFFFFFFF);
  static const Color foreground = Color(0xFF111827);
  static const Color mutedForeground = Color(0xFF6B7280);
  static const Color border = Color(0xFFE5E7EB);
  static const Color inputBackground = Color(0xFFF3F4F6);
  static const Color secondary = Color(0xFFF3F4F6);
  static const Color accent = Color(0xFFE5E7EB);
  static const Color muted = Color(0xFFF3F4F6);
  static const Color primary = Color(0xFF2563EB);
  static const Color destructive = Color(0xFFDC2626);
}

class ApiClient {
  ApiClient({String? baseUrl}) : baseUrl = baseUrl ?? _defaultBaseUrl;

  final String baseUrl;

  static String get _defaultBaseUrl {
    const configured = String.fromEnvironment('API_BASE_URL');
    if (configured.isNotEmpty) {
      return configured;
    }
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://127.0.0.1:8000';
  }

  Future<List<MenuSummary>> searchMenus({
    required double lat,
    required double lng,
    required double radiusKm,
    required String query,
    required SearchMode mode,
    required List<String> keywords,
  }) async {
    final uri = Uri.parse('$baseUrl/api/search').replace(
      queryParameters: <String, String>{
        'lat': lat.toString(),
        'lng': lng.toString(),
        'radius': radiusKm.toString(),
        'radius_km': radiusKm.toString(),
        'query': query,
        'search_mode': mode.label,
        'keywords': keywords.join(','),
      },
    );
    final json = await _getJson(uri);
    final rawResults = json is Map<String, dynamic> ? json['results'] : json;
    if (rawResults is! List) {
      return <MenuSummary>[];
    }
    return rawResults.whereType<Map<String, dynamic>>().map(MenuSummary.fromJson).toList();
  }

  Future<List<RestaurantPin>> fetchRestaurants({
    required double lat,
    required double lng,
    required double radiusKm,
    String query = '',
  }) async {
    final uri = Uri.parse('$baseUrl/api/restaurants').replace(
      queryParameters: <String, String>{
        'lat': lat.toString(),
        'lng': lng.toString(),
        'radius_km': radiusKm.toString(),
        if (query.isNotEmpty) 'query': query,
      },
    );
    final json = await _getJson(uri);
    final raw = json is Map<String, dynamic> ? json['restaurants'] : json;
    if (raw is! List) {
      return <RestaurantPin>[];
    }
    return raw.whereType<Map<String, dynamic>>().map(RestaurantPin.fromJson).toList();
  }

  Future<List<MenuSummary>> fetchRestaurantMenus(
    String resId, {
    required double lat,
    required double lng,
  }) async {
    final uri = Uri.parse('$baseUrl/api/restaurant/$resId/menus').replace(
      queryParameters: <String, String>{
        'lat': lat.toString(),
        'lng': lng.toString(),
      },
    );
    final json = await _getJson(uri);
    final raw = json is Map<String, dynamic> ? json['results'] : json;
    if (raw is! List) {
      return <MenuSummary>[];
    }
    return raw.whereType<Map<String, dynamic>>().map(MenuSummary.fromJson).toList();
  }

  Future<List<CoreInfo>> fetchMenuDetails(String menuId) async {
    final uri = Uri.parse('$baseUrl/api/menu/$menuId/details');
    final json = await _getJson(uri);
    final rawDetails = json is Map<String, dynamic> ? json['details'] : json;
    if (rawDetails is! List) {
      return <CoreInfo>[];
    }
    return rawDetails.whereType<Map<String, dynamic>>().map(CoreInfo.fromJson).toList();
  }

  Future<void> vote({
    required int infoId,
    required String vote,
    required String previous,
  }) async {
    final uri = Uri.parse('$baseUrl/api/vote');
    final response = await http.post(
      uri,
      headers: const <String, String>{
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{
        'info_id': infoId.toInt(),
        'vote': vote,
        'previous': previous,
      }),
    ).timeout(const Duration(seconds: 4));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Vote request failed: ${response.statusCode} ${response.body}');
    }
  }

  Future<List<MenuComment>> fetchComments(int infoId, {String token = ''}) async {
    final uri = Uri.parse('$baseUrl/api/info/$infoId/comments').replace(
      queryParameters: <String, String>{
        if (token.isNotEmpty) 'author_token': token,
      },
    );
    final json = await _getJson(uri);
    final raw = json is Map<String, dynamic> ? json['comments'] : json;
    if (raw is! List) {
      return <MenuComment>[];
    }
    return raw.whereType<Map<String, dynamic>>().map(MenuComment.fromJson).toList();
  }

  Future<MenuComment> addComment(int infoId, String content, {String token = ''}) async {
    final uri = Uri.parse('$baseUrl/api/info/$infoId/comments');
    final response = await http.post(
      uri,
      headers: const <String, String>{
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{'content': content, 'author_token': token}),
    ).timeout(const Duration(seconds: 4));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Comment failed: ${response.statusCode} ${response.body}');
    }
    final json = jsonDecode(utf8.decode(response.bodyBytes));
    final raw = json is Map<String, dynamic> ? json['comment'] : json;
    return MenuComment.fromJson(raw as Map<String, dynamic>);
  }

  Future<MenuComment> updateComment(int commentId, String content, String token) async {
    final uri = Uri.parse('$baseUrl/api/comments/$commentId');
    final response = await http.put(
      uri,
      headers: const <String, String>{
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{'content': content, 'author_token': token}),
    ).timeout(const Duration(seconds: 4));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Comment update failed: ${response.statusCode} ${response.body}');
    }
    final json = jsonDecode(utf8.decode(response.bodyBytes));
    final raw = json is Map<String, dynamic> ? json['comment'] : json;
    return MenuComment.fromJson(raw as Map<String, dynamic>);
  }

  Future<void> deleteComment(int commentId, String token) async {
    final uri = Uri.parse('$baseUrl/api/comments/$commentId').replace(
      queryParameters: <String, String>{'author_token': token},
    );
    final response = await http.delete(uri).timeout(const Duration(seconds: 4));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Comment delete failed: ${response.statusCode} ${response.body}');
    }
  }

  Future<dynamic> _getJson(Uri uri) async {
    final response = await http.get(uri).timeout(const Duration(seconds: 4));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('HTTP ${response.statusCode}');
    }
    if (response.body.isEmpty) {
      return null;
    }
    return jsonDecode(utf8.decode(response.bodyBytes));
  }
}

class MenuSummary {
  MenuSummary({
    required this.menuId,
    required this.resId,
    required this.restaurantName,
    required this.menuName,
    required this.price,
    required this.latitude,
    required this.longitude,
    required this.photoUrl,
    required this.corePros,
    required this.coreCons,
  });

  final String menuId;
  final String resId;
  final String restaurantName;
  final String menuName;
  final int price;
  final double latitude;
  final double longitude;
  final String photoUrl;
  // 대표 장/단점: 상세 화면에서 투표로 (추천-비추천) 순위가 바뀌면 즉시 갱신되어
  // 목록 미리보기에도 새로고침 없이 반영된다.
  String corePros;
  String coreCons;

  String get priceLabel {
    if (price <= 0) {
      return '가격 정보 없음';
    }
    final formatted = price.toString().replaceAllMapped(
      RegExp(r'\B(?=(\d{3})+(?!\d))'),
      (match) => ',',
    );
    return '$formatted원';
  }

  factory MenuSummary.fromJson(Map<String, dynamic> json) {
    return MenuSummary(
      menuId: '${json['menu_id'] ?? ''}',
      resId: '${json['res_id'] ?? ''}',
      restaurantName: '${json['restaurant_name'] ?? ''}',
      menuName: '${json['menu_name'] ?? json['name'] ?? '이름 없는 메뉴'}',
      price: _asInt(json['price'] ?? 0),
      latitude: _asDouble(json['lat'] ?? json['latitude'] ?? 0),
      longitude: _asDouble(json['lng'] ?? json['longitude'] ?? 0),
      photoUrl: '${json['photo_url'] ?? ''}',
      corePros: '${json['core_pros'] ?? ''}',
      coreCons: '${json['core_cons'] ?? ''}',
    );
  }
}

class CoreInfo {
  CoreInfo({
    required this.infoId,
    required this.content,
    required this.infoType,
    required this.level,
    required this.upvotes,
    required this.downvotes,
    this.commentCount = 0,
  });

  final int infoId;
  final String content;
  final String infoType;
  final int level;
  int upvotes;
  int downvotes;
  int commentCount;

  // 이 기기에서 누른 투표 상태: 'none' | 'up' | 'down' (두 번 누르면 취소)
  String userVote = 'none';

  factory CoreInfo.fromJson(Map<String, dynamic> json) {
    return CoreInfo(
      infoId: _asInt(json['info_id'] ?? 0),
      content: '${json['content'] ?? ''}',
      infoType: '${json['info_type'] ?? ''}',
      level: _asInt(json['level'] ?? 0),
      upvotes: _asInt(json['upvotes'] ?? 0),
      downvotes: _asInt(json['downvotes'] ?? 0),
      commentCount: _asInt(json['comment_count'] ?? 0),
    );
  }
}

class MenuComment {
  const MenuComment({
    required this.commentId,
    required this.content,
    required this.createdAt,
    this.isMine = false,
  });

  final int commentId;
  final String content;
  final String createdAt;
  final bool isMine; // 이 기기(작성자)가 단 댓글이면 true → 수정/삭제 버튼 노출

  MenuComment copyWith({String? content}) {
    return MenuComment(
      commentId: commentId,
      content: content ?? this.content,
      createdAt: createdAt,
      isMine: isMine,
    );
  }

  factory MenuComment.fromJson(Map<String, dynamic> json) {
    return MenuComment(
      commentId: _asInt(json['comment_id'] ?? 0),
      content: '${json['content'] ?? ''}',
      createdAt: '${json['created_at'] ?? ''}',
      isMine: json['is_mine'] == true,
    );
  }
}

/// 기기별 익명 작성자 토큰을 영속 저장한다. 서버는 이 토큰으로 작성자를 식별해
/// 본인 댓글만 수정/삭제하도록 검증한다. (웹에서는 localStorage에 저장됨)
class CommentIdentity {
  static const String _key = 'menuwise_comment_token';
  static String? _cache;

  static Future<String> token() async {
    if (_cache != null) return _cache!;
    final prefs = await SharedPreferences.getInstance();
    var token = prefs.getString(_key);
    if (token == null || token.isEmpty) {
      final now = DateTime.now().microsecondsSinceEpoch;
      final rand = Object().hashCode ^ now.hashCode;
      token = 'u_${now.toRadixString(16)}${rand.toRadixString(16)}';
      await prefs.setString(_key, token);
    }
    _cache = token;
    return token;
  }
}

/// 기기별 추천/비추천 상태를 영속 저장해 앱을 나갔다 와도 재투표(무한 증가)를 막는다.
/// (웹에서는 localStorage에 저장됨)
class VoteStore {
  static const String _key = 'menuwise_votes';
  static Map<String, String>? _cache;

  static Future<Map<String, String>> _load() async {
    if (_cache != null) return _cache!;
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.isEmpty) {
      _cache = <String, String>{};
    } else {
      try {
        final decoded = jsonDecode(raw) as Map<String, dynamic>;
        _cache = decoded.map((k, v) => MapEntry(k, '$v'));
      } catch (_) {
        _cache = <String, String>{};
      }
    }
    return _cache!;
  }

  static Future<String> get(int infoId) async {
    final map = await _load();
    return map['$infoId'] ?? 'none';
  }

  static Future<void> set(int infoId, String vote) async {
    final map = await _load();
    if (vote == 'none') {
      map.remove('$infoId');
    } else {
      map['$infoId'] = vote;
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(map));
  }
}

class RestaurantPin {
  const RestaurantPin({
    required this.resId,
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.category,
    required this.menuCount,
  });

  final String resId;
  final String name;
  final double latitude;
  final double longitude;
  final String category;
  final int menuCount;

  factory RestaurantPin.fromJson(Map<String, dynamic> json) {
    return RestaurantPin(
      resId: '${json['res_id'] ?? ''}',
      name: '${json['res_name'] ?? '이름 없는 식당'}',
      latitude: _asDouble(json['lat'] ?? 0),
      longitude: _asDouble(json['lng'] ?? 0),
      category: '${json['category'] ?? ''}',
      menuCount: _asInt(json['menu_count'] ?? 0),
    );
  }
}

String _radiusLabel(int meters) {
  if (meters >= 1000) {
    return '${(meters / 1000).toStringAsFixed(meters % 1000 == 0 ? 0 : 1)}km';
  }
  return '${meters}m';
}

int _asInt(dynamic value) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse('$value') ?? 0;
}

double _asDouble(dynamic value) {
  if (value is double) {
    return value;
  }
  if (value is num) {
    return value.toDouble();
  }
  return double.tryParse('$value') ?? 0;
}

bool get _usesAppleFont {
  if (kIsWeb) {
    return false;
  }
  return defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.macOS;
}