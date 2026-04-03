import 'dart:io';

import 'package:camera/camera.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';

import '../app_config.dart';
import '../services/api_client.dart';
import '../services/api_models.dart';
import '../services/auth_store.dart';
import '../widgets/app_shell.dart';
import '../widgets/gsps_card.dart';

class ClockScreen extends StatefulWidget {
  const ClockScreen({super.key, required this.auth});
  final AuthStore auth;

  @override
  State<ClockScreen> createState() => _ClockScreenState();
}

class _ClockScreenState extends State<ClockScreen> {
  bool _busy = false;
  String? _error;
  List<SiteBrief> _sites = [];
  int? _selectedSiteId;
  bool _isClockIn = true;

  @override
  void initState() {
    super.initState();
    _loadSites();
  }

  Future<void> _loadSites() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final companyId = await widget.auth.getActiveCompanyId();
      if (companyId == null) throw Exception('Select company in Profile first');
      final api = ApiClient(widget.auth);
      final res = await api.dio.get('/sites', queryParameters: {'company_id': companyId});
      final arr = (res.data as List).cast<Map<String, dynamic>>();
      _sites = arr.map(SiteBrief.fromJson).toList();
      _selectedSiteId ??= _sites.isNotEmpty ? _sites.first.id : null;
    } on DioException catch (e) {
      _error = e.response?.data?.toString() ?? e.message;
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _clock() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final companyId = await widget.auth.getActiveCompanyId();
      if (companyId == null) throw Exception('Select company in Profile first');

      // Permissions
      final loc = await Permission.locationWhenInUse.request();
      if (!loc.isGranted) throw Exception('Location permission required');
      final cam = await Permission.camera.request();
      if (!cam.isGranted) throw Exception('Camera permission required');

      // Location
      final pos = await Geolocator.getCurrentPosition(desiredAccuracy: LocationAccuracy.high);

      // Camera capture (front/back selection handled by OS default; you can enhance later)
      final cameras = await availableCameras();
      if (cameras.isEmpty) throw Exception('No camera available');
      final controller = CameraController(cameras.first, ResolutionPreset.medium, enableAudio: false);
      await controller.initialize();
      final shot = await controller.takePicture();
      await controller.dispose();

      // Geofence check vs selected site (if site has lat/lng)
      double? siteLat;
      double? siteLng;
      if (_selectedSiteId != null) {
        final s = _sites.firstWhere((x) => x.id == _selectedSiteId, orElse: () => _sites.first);
        siteLat = s.lat;
        siteLng = s.lng;
      }

      bool withinFence = true;
      double? distanceMeters;
      if (siteLat != null && siteLng != null) {
        distanceMeters = Geolocator.distanceBetween(
          pos.latitude,
          pos.longitude,
          siteLat,
          siteLng,
        );
        withinFence = distanceMeters <= AppConfig.geofenceRadiusMeters;
      }

      final api = ApiClient(widget.auth);
      final form = FormData.fromMap({
        'event_type': _isClockIn ? 'clock_in' : 'clock_out',
        'site_id': _selectedSiteId,
        'lat': pos.latitude,
        'lng': pos.longitude,
        'accuracy_m': pos.accuracy,
        'device_time': DateTime.now().toIso8601String(),
        'distance_m': distanceMeters,
        'within_geofence': withinFence,
        'photo': await MultipartFile.fromFile(shot.path, filename: 'clock.jpg'),
      });
      await api.dio.post(
        '/clock/events',
        queryParameters: {'company_id': companyId},
        data: form,
      );

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_isClockIn ? 'Clocked in' : 'Clocked out')),
        );
      }
    } on DioException catch (e) {
      _error = e.response?.data?.toString() ?? e.message;
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      auth: widget.auth,
      title: 'Clock',
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_busy) const LinearProgressIndicator(),
          if (_error != null)
            GspsCard(title: 'Error', subtitle: 'Fix the issue and try again.', child: Text(_error!)),
          GspsCard(
            title: _isClockIn ? 'Clock in' : 'Clock out',
            subtitle: 'GPS + Camera required. Geofence radius: ${AppConfig.geofenceRadiusMeters.toStringAsFixed(0)}m',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(value: true, label: Text('Clock in')),
                    ButtonSegment(value: false, label: Text('Clock out')),
                  ],
                  selected: {_isClockIn},
                  onSelectionChanged: _busy ? null : (s) => setState(() => _isClockIn = s.first),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<int>(
                  value: _selectedSiteId,
                  items: _sites
                      .map((s) => DropdownMenuItem(value: s.id, child: Text(s.name)))
                      .toList(),
                  onChanged: _busy ? null : (v) => setState(() => _selectedSiteId = v),
                  decoration: const InputDecoration(
                    labelText: 'Site',
                    helperText: 'Recommended. Enables distance/geofence validation.',
                    prefixIcon: Icon(Icons.place_outlined),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _busy ? null : _clock,
                    icon: Icon(_isClockIn ? Icons.login : Icons.logout),
                    label: Text(_isClockIn ? 'Clock in now' : 'Clock out now'),
                  ),
                ),
              ],
            ),
          ),
          if (Platform.isAndroid)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text(
                'Tip: For real devices, set API_BASE_URL to your server IP.',
              ),
            ),
        ],
      ),
    );
  }
}

