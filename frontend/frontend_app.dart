import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:pointer_interceptor/pointer_interceptor.dart';

import 'package:menu_wise/kakao_map_canvas.dart'
    if (dart.library.io) 'package:menu_wise/kakao_map_canvas_native.dart'
    if (dart.library.js_interop) 'package:menu_wise/kakao_map_canvas_web.dart';

const String _kakaoMapKey = String.fromEnvironment('KAKAO_MAP_KEY');
const String _kakaoJavaScriptKey = String.fromEnvironment('KAKAO_JAVASCRIPT_KEY');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeKakaoMaps(_kakaoMapKey);

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
    TasteKeyword('sweet', '달콤함', '🍯'),
    TasteKeyword('spicy', '매콤함', '🌶️'),
    TasteKeyword('sour', '새콤함', '🍋'),
    TasteKeyword('crispy', '바삭함', '✨'),
    TasteKeyword('soft', '부드러움', '🥚'),
    TasteKeyword('savory', '구수함', '🍜'),
  ];

  double _lat = 37.5665;
  double _lng = 126.9780;
  int _searchRadiusMeters = 500;
  bool _showSettings = false;
  bool _isLoading = false;
  bool _isLocating = false;
  bool _sheetOpen = false;
  String? _errorMessage;
  MenuSummary? _selectedMenu;
  List<MenuSummary> _menus = <MenuSummary>[];

  @override
  void initState() {
    super.initState();
    _loadCurrentLocationAndSearch();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final results = await _api.searchMenus(
        lat: _lat,
        lng: _lng,
        radiusKm: _searchRadiusMeters / 1000,
        query: _searchController.text.trim(),
        mode: SearchMode.menu,
        keywords: _selectedKeywords.toList()..sort(),
      );

      if (!mounted) {
        return;
      }

      setState(() {
        _menus = _filterLocally(results);
        _sheetOpen = _menus.isNotEmpty;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _menus = <MenuSummary>[];
        _sheetOpen = false;
        _errorMessage = 'FastAPI 서버에 연결할 수 없습니다. ${_api.baseUrl} 상태를 확인해 주세요.';
      });
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  Future<void> _loadCurrentLocationAndSearch() async {
    setState(() => _isLocating = true);

    try {
      final position = await _getCurrentPosition();
      if (!mounted) {
        return;
      }
      setState(() {
        _lat = position.latitude;
        _lng = position.longitude;
      });
    } catch (_) {
      // Keep the Seoul fallback when location is unavailable or permission is denied.
    } finally {
      if (mounted) {
        setState(() => _isLocating = false);
      }
    }

    await _search();
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

  List<MenuSummary> _filterLocally(List<MenuSummary> source) {
    Iterable<MenuSummary> filtered = source;
    final query = _searchController.text.trim().toLowerCase();

    if (query.isNotEmpty) {
      filtered = filtered.where((menu) {
        final text = '${menu.menuName} ${menu.corePros} ${menu.coreCons}'.toLowerCase();
        return text.contains(query);
      });
    }

    if (_selectedKeywords.isNotEmpty) {
      filtered = filtered.where((menu) {
        final text = '${menu.menuName} ${menu.corePros} ${menu.coreCons}'.toLowerCase();
        return _selectedKeywords.any((keyword) => text.contains(keyword.toLowerCase()));
      });
    }

    return filtered.toList();
  }

  void _toggleKeyword(TasteKeyword keyword) {
    setState(() {
      if (!_selectedKeywords.add(keyword.label)) {
        _selectedKeywords.remove(keyword.label);
      }
    });
    _search();
  }

  void _openSheet() {
    if (_menus.isEmpty) {
      _search();
      return;
    }
    setState(() => _sheetOpen = true);
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
                  onSearch: _search,
                  onToggleSettings: () => setState(() => _showSettings = !_showSettings),
                  onRadiusChange: (radius) => setState(() => _searchRadiusMeters = radius),
                  onRadiusChangeEnd: (_) => _search(),
                ),
                KeywordBanner(
                  keywords: _keywords,
                  selectedKeywords: _selectedKeywords,
                  onToggle: _toggleKeyword,
                ),
                Expanded(
                  child: MapView(
                    menus: _menus,
                    latitude: _lat,
                    longitude: _lng,
                    radiusMeters: _searchRadiusMeters,
                    isLoading: _isLoading || _isLocating,
                    errorMessage: _errorMessage,
                    onPinTap: _openSheet,
                    onRetry: _search,
                  ),
                ),
              ],
            ),
            if (_sheetOpen)
              PointerInterceptor(
                child: RestaurantSheet(
                  menus: _menus,
                  radiusMeters: _searchRadiusMeters,
                  onClose: () => setState(() => _sheetOpen = false),
                  onMenuSelect: (menu) => setState(() => _selectedMenu = menu),
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

class FigmaSearchBar extends StatelessWidget {
  const FigmaSearchBar({
    super.key,
    required this.controller,
    required this.searchRadiusMeters,
    required this.showSettings,
    required this.isLoading,
    required this.onSearch,
    required this.onToggleSettings,
    required this.onRadiusChange,
    required this.onRadiusChangeEnd,
  });

  final TextEditingController controller;
  final int searchRadiusMeters;
  final bool showSettings;
  final bool isLoading;
  final VoidCallback onSearch;
  final VoidCallback onToggleSettings;
  final ValueChanged<int> onRadiusChange;
  final ValueChanged<int> onRadiusChangeEnd;

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
                      decoration: const InputDecoration(
                        icon: Icon(Icons.search, color: AppColors.mutedForeground),
                        hintText: '음식점 또는 메뉴 검색',
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
                            max: 2000,
                            divisions: 19,
                            value: searchRadiusMeters.toDouble(),
                            label: _radiusLabel(searchRadiusMeters),
                            onChanged: (value) => onRadiusChange(value.round()),
                            onChangeEnd: (value) => onRadiusChangeEnd(value.round()),
                          ),
                          const Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: <Widget>[
                              Text('100m', style: TextStyle(fontSize: 12, color: AppColors.mutedForeground)),
                              Text('2km', style: TextStyle(fontSize: 12, color: AppColors.mutedForeground)),
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
      message: keyword.label,
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
                    keyword.label,
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
    required this.menus,
    required this.latitude,
    required this.longitude,
    required this.radiusMeters,
    required this.isLoading,
    required this.errorMessage,
    required this.onPinTap,
    required this.onRetry,
  });

  final List<MenuSummary> menus;
  final double latitude;
  final double longitude;
  final int radiusMeters;
  final bool isLoading;
  final String? errorMessage;
  final VoidCallback onPinTap;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final visiblePins = math.min(menus.length, 5);

    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        KakaoMapCanvas(
          nativeKey: _kakaoMapKey,
          javaScriptKey: _kakaoJavaScriptKey,
          latitude: latitude,
          longitude: longitude,
        ),
        for (int i = 0; i < visiblePins; i++)
          _MapPin(
            menu: menus[i],
            position: _pinPosition(i),
            onTap: onPinTap,
          ),
        if (isLoading)
          const Center(child: CircularProgressIndicator())
        else if (menus.isEmpty)
          Center(
            child: MapNotice(
              icon: errorMessage == null ? Icons.nearby_error_outlined : Icons.cloud_off_outlined,
              title: errorMessage == null ? '검색 결과가 없습니다' : '서버 연결이 필요합니다',
              message: errorMessage ?? '검색어와 키워드를 바꿔 다시 시도해 보세요.',
              onRetry: onRetry,
            ),
          ),
        Positioned(
          right: 16,
          bottom: 16,
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
                Text('${_radiusLabel(radiusMeters)} 이내 ${menus.length}개'),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _MapPin extends StatelessWidget {
  const _MapPin({required this.menu, required this.position, required this.onTap});

  final MenuSummary menu;
  final Offset position;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: position.dx,
      top: position.dy,
      child: FractionalTranslation(
        translation: const Offset(-0.5, -1),
        child: GestureDetector(
          onTap: onTap,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Container(
                padding: const EdgeInsets.all(8),
                decoration: const BoxDecoration(
                  color: AppColors.destructive,
                  shape: BoxShape.circle,
                  boxShadow: <BoxShadow>[
                    BoxShadow(color: Color(0x33000000), blurRadius: 12, offset: Offset(0, 5)),
                  ],
                ),
                child: const Icon(Icons.location_pin, color: Colors.white, size: 20),
              ),
              const SizedBox(height: 4),
              Container(
                constraints: const BoxConstraints(maxWidth: 120),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
                decoration: BoxDecoration(
                  color: AppColors.background,
                  borderRadius: BorderRadius.circular(5),
                  border: Border.all(color: AppColors.border),
                  boxShadow: const <BoxShadow>[
                    BoxShadow(color: Color(0x17000000), blurRadius: 8, offset: Offset(0, 3)),
                  ],
                ),
                child: Text(
                  menu.menuName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class RestaurantSheet extends StatelessWidget {
  const RestaurantSheet({
    super.key,
    required this.menus,
    required this.radiusMeters,
    required this.onClose,
    required this.onMenuSelect,
  });

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
                        const Text('근처 추천 메뉴', style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
                        Text(
                          '${_radiusLabel(radiusMeters)} · 메뉴 ${menus.length}개',
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
  late Future<List<CoreInfo>> _details;
  DetailTab _activeTab = DetailTab.positive;

  @override
  void initState() {
    super.initState();
    _details = widget.api.fetchMenuDetails(widget.menu.menuId);
  }

  Future<void> _vote(CoreInfo info, bool isUpvote) async {
    try {
      await widget.api.vote(infoId: info.infoId, isUpvote: isUpvote);
      setState(() {
        if (isUpvote) {
          info.upvotes += 1;
        } else {
          info.downvotes += 1;
        }
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
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
          Expanded(
            child: FutureBuilder<List<CoreInfo>>(
              future: _details,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return const Center(child: Text('상세 리뷰를 불러오지 못했습니다.'));
                }

                final details = (snapshot.data ?? <CoreInfo>[])
                    .where((item) => _activeTab == DetailTab.positive ? item.infoType == 'PROS' : item.infoType == 'CONS')
                    .toList();

                if (details.isEmpty) {
                  return const Center(child: Text('아직 상세 리뷰 요약이 없습니다.'));
                }

                return ListView.separated(
                  padding: const EdgeInsets.all(16),
                  itemBuilder: (context, index) {
                    final info = details[index];
                    return ReviewCard(
                      info: info,
                      onLike: () => _vote(info, true),
                      onDislike: () => _vote(info, false),
                    );
                  },
                  separatorBuilder: (context, index) => const SizedBox(height: 14),
                  itemCount: details.length,
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class ReviewCard extends StatelessWidget {
  const ReviewCard({
    super.key,
    required this.info,
    required this.onLike,
    required this.onDislike,
  });

  final CoreInfo info;
  final VoidCallback onLike;
  final VoidCallback onDislike;

  @override
  Widget build(BuildContext context) {
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
              CountButton(icon: Icons.thumb_up_alt_outlined, count: info.upvotes, onTap: onLike),
              const SizedBox(width: 10),
              CountButton(icon: Icons.thumb_down_alt_outlined, count: info.downvotes, onTap: onDislike),
              const SizedBox(width: 10),
              CountButton(icon: Icons.mode_comment_outlined, count: 0, onTap: () {}),
            ],
          ),
        ],
      ),
    );
  }
}

class CountButton extends StatelessWidget {
  const CountButton({super.key, required this.icon, required this.count, required this.onTap});

  final IconData icon;
  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.background,
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icon, size: 17),
              const SizedBox(width: 6),
              Text('$count'),
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
            text.isEmpty ? '리뷰 요약 준비 중' : text,
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
  const TasteKeyword(this.id, this.label, this.emoji);

  final String id;
  final String label;
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

  Future<List<CoreInfo>> fetchMenuDetails(String menuId) async {
    final uri = Uri.parse('$baseUrl/api/menu/$menuId/details');
    final json = await _getJson(uri);
    final rawDetails = json is Map<String, dynamic> ? json['details'] : json;
    if (rawDetails is! List) {
      return <CoreInfo>[];
    }
    return rawDetails.whereType<Map<String, dynamic>>().map(CoreInfo.fromJson).toList();
  }

  Future<void> vote({required int infoId, required bool isUpvote}) async {
    final uri = Uri.parse('$baseUrl/api/vote');
    final response = await http.post(
      uri,
      headers: const <String, String>{
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{
        'info_id': infoId.toInt(),
        'upvote': isUpvote,
      }),
    ).timeout(const Duration(seconds: 4));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Vote request failed: ${response.statusCode} ${response.body}');
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
  const MenuSummary({
    required this.menuId,
    required this.menuName,
    required this.price,
    required this.photoUrl,
    required this.corePros,
    required this.coreCons,
  });

  final String menuId;
  final String menuName;
  final int price;
  final String photoUrl;
  final String corePros;
  final String coreCons;

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
      menuName: '${json['menu_name'] ?? json['name'] ?? '이름 없는 메뉴'}',
      price: _asInt(json['price']),
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
  });

  final int infoId;
  final String content;
  final String infoType;
  final int level;
  int upvotes;
  int downvotes;

  factory CoreInfo.fromJson(Map<String, dynamic> json) {
    return CoreInfo(
      infoId: _asInt(json['info_id']),
      content: '${json['content'] ?? ''}',
      infoType: '${json['info_type'] ?? ''}',
      level: _asInt(json['level']),
      upvotes: _asInt(json['upvotes']),
      downvotes: _asInt(json['downvotes']),
    );
  }
}

Offset _pinPosition(int index) {
  const positions = <Offset>[
    Offset(130, 210),
    Offset(260, 155),
    Offset(190, 305),
    Offset(315, 250),
    Offset(95, 360),
  ];
  return positions[index % positions.length];
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

bool get _usesAppleFont {
  if (kIsWeb) {
    return false;
  }
  return defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.macOS;
}
