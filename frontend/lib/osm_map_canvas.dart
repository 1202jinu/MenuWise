import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

/// 지도 위에 찍히는 마커 한 개. (지도 구현체와 앱 코드를 분리하기 위한 단순 모델)
class MapMarker {
  const MapMarker({
    required this.id,
    required this.title,
    required this.latitude,
    required this.longitude,
    required this.onTap,
  });

  final String id;
  final String title;
  final double latitude;
  final double longitude;
  final VoidCallback onTap;
}

/// OpenStreetMap 기반 무료 지도 캔버스(API 키 불필요).
/// 카메라 중심(camera*) + 검색 반경 원(user*) + 식당 이름 마커를 그린다.
class OsmMapCanvas extends StatefulWidget {
  const OsmMapCanvas({
    super.key,
    required this.cameraLat,
    required this.cameraLng,
    required this.userLat,
    required this.userLng,
    required this.radiusMeters,
    required this.markers,
  });

  final double cameraLat;
  final double cameraLng;
  final double userLat;
  final double userLng;
  final int radiusMeters;
  final List<MapMarker> markers;

  @override
  State<OsmMapCanvas> createState() => _OsmMapCanvasState();
}

class _OsmMapCanvasState extends State<OsmMapCanvas> {
  final MapController _controller = MapController();

  @override
  void didUpdateWidget(OsmMapCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 카메라 중심이 바뀌면 지도를 그 위치로 이동한다(식당 선택/메뉴 이동 등).
    if (oldWidget.cameraLat != widget.cameraLat || oldWidget.cameraLng != widget.cameraLng) {
      _controller.move(
        LatLng(widget.cameraLat, widget.cameraLng),
        _controller.camera.zoom,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return FlutterMap(
      mapController: _controller,
      options: MapOptions(
        initialCenter: LatLng(widget.cameraLat, widget.cameraLng),
        initialZoom: 15,
        minZoom: 3,
        maxZoom: 18,
      ),
      children: <Widget>[
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.menuwise.app',
        ),
        CircleLayer(
          circles: <CircleMarker>[
            CircleMarker(
              point: LatLng(widget.userLat, widget.userLng),
              radius: widget.radiusMeters.toDouble(),
              useRadiusInMeter: true,
              color: const Color(0x142563EB),
              borderColor: const Color(0x552563EB),
              borderStrokeWidth: 1,
            ),
          ],
        ),
        MarkerLayer(
          markers: <Marker>[
            for (final marker in widget.markers)
              Marker(
                point: LatLng(marker.latitude, marker.longitude),
                width: 130,
                height: 56,
                alignment: Alignment.topCenter,
                child: GestureDetector(
                  onTap: marker.onTap,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      const Icon(Icons.location_pin, color: Color(0xFFDC2626), size: 30),
                      Container(
                        constraints: const BoxConstraints(maxWidth: 126),
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(5),
                          border: Border.all(color: const Color(0xFFE5E7EB)),
                          boxShadow: const <BoxShadow>[
                            BoxShadow(color: Color(0x14000000), blurRadius: 4, offset: Offset(0, 1)),
                          ],
                        ),
                        child: Text(
                          marker.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }
}
