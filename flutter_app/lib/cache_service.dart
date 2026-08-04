/// Офлайн-кеширование записей и статистики
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'models.dart';

class CacheService {
  static const _entriesKey = 'cached_entries';
  static const _statsKey = 'cached_stats';
  static const _lastSyncKey = 'last_sync_time';

  /// Сохранить записи в кеш
  static Future<void> cacheEntries(List<DiaryEntry> entries) async {
    final prefs = await SharedPreferences.getInstance();
    final json = jsonEncode(entries.map((e) => e.toJson()).toList());
    await prefs.setString(_entriesKey, json);
    await prefs.setString(_lastSyncKey, DateTime.now().toIso8601String());
  }

  /// Загрузить записи из кеша
  static Future<List<DiaryEntry>> getCachedEntries() async {
    final prefs = await SharedPreferences.getInstance();
    final json = prefs.getString(_entriesKey);
    if (json == null || json.isEmpty) return [];
    try {
      final list = jsonDecode(json) as List;
      return list.map((e) => DiaryEntry.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  /// Сохранить статистику в кеш
  static Future<void> cacheStats(Stats stats) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_statsKey, jsonEncode(stats.toJson()));
  }

  /// Загрузить статистику из кеша
  static Future<Stats?> getCachedStats() async {
    final prefs = await SharedPreferences.getInstance();
    final json = prefs.getString(_statsKey);
    if (json == null || json.isEmpty) return null;
    try {
      return Stats.fromJson(jsonDecode(json) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  /// Время последней синхронизации
  static Future<String?> getLastSyncTime() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_lastSyncKey);
  }

  /// Очистить кеш
  static Future<void> clearCache() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_entriesKey);
    await prefs.remove(_statsKey);
    await prefs.remove(_lastSyncKey);
  }
}
