/// Конфигурация приложения «Мой путь»
class AppConfig {
  /// Базовый URL API. Меняется в настройках.
  /// По умолчанию — WSL IP (для отладки на эмуляторе/USB).
  /// Для телефона в той же WiFi-сети — Windows IP:8001
  static const String defaultApiUrl = 'http://10.213.156.81:8001';

  static const String appVersion = '1.0.0';
  static const String appName = 'Мой путь';

  /// Ключ в SharedPreferences
  static const String apiUrlKey = 'api_url';
  static const String tokenKey = 'auth_token';
  static const String userNameKey = 'user_name';
  static const String userIdKey = 'user_id';
}