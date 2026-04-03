import 'package:dio/dio.dart';

import '../app_config.dart';
import 'auth_store.dart';

class ApiClient {
  ApiClient(this._auth)
      : dio = Dio(
          BaseOptions(
            baseUrl: '${AppConfig.apiBaseUrl}/api/v1',
            connectTimeout: const Duration(seconds: 20),
            receiveTimeout: const Duration(seconds: 30),
          ),
        ) {
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _auth.getToken();
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
      ),
    );
  }

  final AuthStore _auth;
  final Dio dio;
}

