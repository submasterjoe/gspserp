class AppConfig {
  /// Example: http://192.168.1.10:8000
  /// For Android emulator + local backend: http://10.0.2.2:8000
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Default radius for geofence check (meters)
  static const double geofenceRadiusMeters = 200.0;
}

