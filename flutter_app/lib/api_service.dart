/// API-сервис для «Мой путь»
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'config.dart';
import 'models.dart';

class ApiService {
  static String _apiUrl = AppConfig.defaultApiUrl;
  static String _token = '';

  static Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    // Always use default API URL — ignore any saved local IP from development
    _apiUrl = AppConfig.defaultApiUrl;
    _token = prefs.getString(AppConfig.tokenKey) ?? '';
  }

  static Future<void> setApiUrl(String url) async {
    _apiUrl = url;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConfig.apiUrlKey, url);
  }

  static String get apiUrl => _apiUrl;
  static String get token => _token;

  static bool get isLoggedIn => _token.isNotEmpty;

  static Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (_token.isNotEmpty) 'Authorization': 'Bearer $_token',
  };

  // ── Auth ──────────────────────────────────────────────
  static Future<Map<String, dynamic>> register(String phone, String name, String password, {bool consent = false}) async {
    final resp = await http.post(
      Uri.parse('$_apiUrl/auth/register'),
      headers: _headers,
      body: jsonEncode({'phone': phone, 'name': name, 'password': password, 'consent': consent}),
    );
    if (resp.statusCode != 200) {
      throw Exception(jsonDecode(resp.body)['detail'] ?? 'Ошибка регистрации');
    }
    final data = jsonDecode(resp.body);
    await _saveAuth(data);
    return data;
  }

  static Future<Map<String, dynamic>> login(String phone, String password) async {
    final resp = await http.post(
      Uri.parse('$_apiUrl/auth/login'),
      headers: _headers,
      body: jsonEncode({'phone': phone, 'password': password}),
    );
    if (resp.statusCode != 200) {
      throw Exception(jsonDecode(resp.body)['detail'] ?? 'Ошибка входа');
    }
    final data = jsonDecode(resp.body);
    await _saveAuth(data);
    return data;
  }

  static Future<void> logout() async {
    _token = '';
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(AppConfig.tokenKey);
    await prefs.remove(AppConfig.userNameKey);
    await prefs.remove(AppConfig.userIdKey);
  }

  static Future<void> _saveAuth(Map<String, dynamic> data) async {
    _token = data['access_token'] as String;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConfig.tokenKey, _token);
    await prefs.setString(AppConfig.userNameKey, data['name'] as String);
    await prefs.setInt(AppConfig.userIdKey, data['user_id'] as int);
    // Save onboarding status from server
    final onboardDone = data['onboarding_completed'] as bool? ?? false;
    await prefs.setBool(AppConfig.onboardingDoneKey, onboardDone);
  }

  static Future<String?> getUserName() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(AppConfig.userNameKey);
  }

  // ── Download (export, biography PDF) ───────────────────
  // Файл требует Authorization-заголовок — нельзя открыть напрямую
  // во внешнем браузере (там нет токена), скачиваем внутри приложения.
  static Future<String> downloadFile(String path, String filename) async {
    final resp = await http.get(Uri.parse('$_apiUrl$path'), headers: _headers);
    if (resp.statusCode != 200) {
      String detail = 'Ошибка загрузки (${resp.statusCode})';
      try {
        detail = jsonDecode(resp.body)['detail'] ?? detail;
      } catch (_) {}
      throw Exception(detail);
    }
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/$filename');
    await file.writeAsBytes(resp.bodyBytes);
    return file.path;
  }

  // ── STT ───────────────────────────────────────────────
  static Future<String> transcribeAudio(File audioFile) async {
    final req = http.MultipartRequest(
      'POST',
      Uri.parse('$_apiUrl/stt/transcribe'),
    );
    req.headers['Authorization'] = 'Bearer $_token';
    req.files.add(await http.MultipartFile.fromPath('file', audioFile.path));
    final resp = await req.send();
    if (resp.statusCode != 200) {
      final body = await resp.stream.bytesToString();
      throw Exception(jsonDecode(body)['detail'] ?? 'Ошибка распознавания');
    }
    final body = await resp.stream.bytesToString();
    return jsonDecode(body)['text'] as String;
  }

  // ── AI Process ────────────────────────────────────────
  static Future<ProcessResult> processEntry(String text) async {
    final resp = await http.post(
      Uri.parse('$_apiUrl/entries/process'),
      headers: _headers,
      body: jsonEncode({'text': text}),
    );
    if (resp.statusCode != 200) {
      throw Exception(jsonDecode(resp.body)['detail'] ?? 'Ошибка AI-обработки');
    }
    return ProcessResult.fromJson(jsonDecode(resp.body));
  }

  // ── Entries CRUD ──────────────────────────────────────
  static Future<DiaryEntry> createEntry(DiaryEntry entry) async {
    final resp = await http.post(
      Uri.parse('$_apiUrl/entries'),
      headers: _headers,
      body: jsonEncode(entry.toJson()),
    );
    if (resp.statusCode != 200) {
      throw Exception('Ошибка сохранения записи');
    }
    return DiaryEntry.fromJson(jsonDecode(resp.body));
  }

  static Future<List<DiaryEntry>> listEntries({
    String dateFrom = '',
    String dateTo = '',
    String tag = '',
    int moodMin = 0,
    int moodMax = 10,
    int limit = 50,
    int offset = 0,
  }) async {
    final params = <String, String>{};
    if (dateFrom.isNotEmpty) params['date_from'] = dateFrom;
    if (dateTo.isNotEmpty) params['date_to'] = dateTo;
    if (tag.isNotEmpty) params['tag'] = tag;
    if (moodMin > 0) params['mood_min'] = moodMin.toString();
    if (moodMax < 10) params['mood_max'] = moodMax.toString();
    params['limit'] = limit.toString();
    params['offset'] = offset.toString();

    final uri = Uri.parse('$_apiUrl/entries').replace(queryParameters: params);
    final resp = await http.get(uri, headers: _headers);
    if (resp.statusCode != 200) {
      throw Exception('Ошибка загрузки записей');
    }
    final list = jsonDecode(resp.body) as List;
    return list.map((e) => DiaryEntry.fromJson(e as Map<String, dynamic>)).toList();
  }

  static Future<DiaryEntry> getEntry(int id) async {
    final resp = await http.get(Uri.parse('$_apiUrl/entries/$id'), headers: _headers);
    if (resp.statusCode != 200) throw Exception('Запись не найдена');
    return DiaryEntry.fromJson(jsonDecode(resp.body));
  }

  static Future<void> updateEntry(int id, DiaryEntry entry) async {
    final resp = await http.put(
      Uri.parse('$_apiUrl/entries/$id'),
      headers: _headers,
      body: jsonEncode(entry.toJson()),
    );
    if (resp.statusCode != 200) throw Exception('Ошибка обновления');
  }

  static Future<void> deleteEntry(int id) async {
    final resp = await http.delete(Uri.parse('$_apiUrl/entries/$id'), headers: _headers);
    if (resp.statusCode != 200) throw Exception('Ошибка удаления');
  }

  // ── Search ────────────────────────────────────────────
  static Future<String> searchDiary(String query) async {
    final resp = await http.post(
      Uri.parse('$_apiUrl/search'),
      headers: _headers,
      body: jsonEncode({'query': query}),
    );
    if (resp.statusCode != 200) {
      throw Exception(jsonDecode(resp.body)['detail'] ?? 'Ошибка поиска');
    }
    return jsonDecode(resp.body)['answer'] as String;
  }

  // ── Biography ─────────────────────────────────────────
  static Future<String> generateBiography() async {
    final resp = await http.post(
      Uri.parse('$_apiUrl/biography/generate'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw Exception(jsonDecode(resp.body)['detail'] ?? 'Ошибка генерации');
    }
    return jsonDecode(resp.body)['content'] as String;
  }

  static Future<String> getBiography() async {
    final resp = await http.get(Uri.parse('$_apiUrl/biography'), headers: _headers);
    if (resp.statusCode != 200) throw Exception('Ошибка загрузки биографии');
    final data = jsonDecode(resp.body);
    return (data['content'] ?? '') as String;
  }

  static Future<void> updateBiography(String content) async {
    final resp = await http.put(
      Uri.parse('$_apiUrl/biography'),
      headers: _headers,
      body: jsonEncode({'content': content}),
    );
    if (resp.statusCode != 200) throw Exception('Ошибка сохранения');
  }

  // ── Stats ─────────────────────────────────────────────
  static Future<Stats> getStats({String period = 'month'}) async {
    final resp = await http.get(
      Uri.parse('$_apiUrl/stats?period=$period'),
      headers: _headers,
    );
    if (resp.statusCode != 200) throw Exception('Ошибка статистики');
    return Stats.fromJson(jsonDecode(resp.body));
  }

  // ── Health ────────────────────────────────────────────
  static Future<bool> checkHealth() async {
    try {
      final resp = await http.get(Uri.parse('$_apiUrl/health'), headers: _headers);
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ── Subscription ──────────────────────────────────────
  static Future<Map<String, dynamic>> getSubscription() async {
    final resp = await http.get(Uri.parse('$_apiUrl/subscription'), headers: _headers);
    if (resp.statusCode != 200) {
      throw Exception('Ошибка загрузки подписки');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  static Future<void> upgradeSubscription() async {
    final resp = await http.post(
      Uri.parse('$_apiUrl/subscription/upgrade'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw Exception('Ошибка обновления подписки');
    }
  }

  // ── Account ────────────────────────────────────────────
  static Future<void> deleteAccount() async {
    final resp = await http.delete(
      Uri.parse('$_apiUrl/account'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw Exception(jsonDecode(resp.body)['detail'] ?? 'Ошибка удаления аккаунта');
    }
    await logout();
  }

  // ── Referral ───────────────────────────────────────────
  static Future<String> getReferralCode() async {
    final resp = await http.get(
      Uri.parse('$_apiUrl/referral/code'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw Exception(jsonDecode(resp.body)['detail'] ?? 'Ошибка получения кода');
    }
    return jsonDecode(resp.body)['code'] as String;
  }

  static Future<Map<String, dynamic>> applyReferralCode(String code) async {
    final resp = await http.post(
      Uri.parse('$_apiUrl/referral/apply'),
      headers: _headers,
      body: jsonEncode({'code': code}),
    );
    if (resp.statusCode != 200) {
      throw Exception(jsonDecode(resp.body)['detail'] ?? 'Ошибка активации кода');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  static Future<ReferralInfo> getReferralStats() async {
    final resp = await http.get(
      Uri.parse('$_apiUrl/referral/stats'),
      headers: _headers,
    );
    if (resp.statusCode != 200) {
      throw Exception(jsonDecode(resp.body)['detail'] ?? 'Ошибка загрузки статистики');
    }
    return ReferralInfo.fromJson(jsonDecode(resp.body));
  }

  // ── Onboarding ─────────────────────────────────────────
  static Future<void> completeOnboarding() async {
    try {
      await http.post(
        Uri.parse('$_apiUrl/auth/onboarding/complete'),
        headers: _headers,
      );
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(AppConfig.onboardingDoneKey, true);
    } catch (_) {
      // If server call fails, still mark locally
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(AppConfig.onboardingDoneKey, true);
    }
  }

  // ── App Update ─────────────────────────────────────────
  static Future<Map<String, dynamic>> checkUpdate() async {
    try {
      final resp = await http.get(
        Uri.parse('$_apiUrl/app/version'),
        headers: _headers,
      ).timeout(const Duration(seconds: 5));
      if (resp.statusCode == 200) {
        return jsonDecode(resp.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return {};
  }
}