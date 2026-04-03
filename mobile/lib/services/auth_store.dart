import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthStore extends ChangeNotifier {
  static const _tokenKey = 'access_token';
  static const _companyIdKey = 'active_company_id';

  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  String? _cachedToken;
  int? _cachedCompanyId;

  Future<String?> getToken() async {
    _cachedToken ??= await _storage.read(key: _tokenKey);
    return _cachedToken;
  }

  Future<bool> hasToken() async {
    final t = await getToken();
    return t != null && t.isNotEmpty;
  }

  Future<void> setToken(String token) async {
    _cachedToken = token;
    await _storage.write(key: _tokenKey, value: token);
    notifyListeners();
  }

  Future<void> clear() async {
    _cachedToken = null;
    _cachedCompanyId = null;
    await _storage.delete(key: _tokenKey);
    await _storage.delete(key: _companyIdKey);
    notifyListeners();
  }

  Future<int?> getActiveCompanyId() async {
    if (_cachedCompanyId != null) return _cachedCompanyId;
    final raw = await _storage.read(key: _companyIdKey);
    if (raw == null || raw.isEmpty) return null;
    _cachedCompanyId = int.tryParse(raw);
    return _cachedCompanyId;
  }

  Future<void> setActiveCompanyId(int companyId) async {
    _cachedCompanyId = companyId;
    await _storage.write(key: _companyIdKey, value: companyId.toString());
    notifyListeners();
  }
}

