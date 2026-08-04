/// Конфигурация приложения «Мой путь»
class AppConfig {
  /// Базовый URL API. Меняется в настройках.
  static const String defaultApiUrl = 'https://moy-way.ru';

  static const String appVersion = '2.2.0';
  static const int versionCode = 220;
  static const String appName = 'Мой путь';

  /// Ключ в SharedPreferences
  static const String apiUrlKey = 'api_url';
  static const String tokenKey = 'auth_token';
  static const String userNameKey = 'user_name';
  static const String userIdKey = 'user_id';
  static const String skippedVersionKey = 'skipped_version';
  static const String installedVersionKey = 'installed_version';
  static const String onboardingDoneKey = 'onboarding_done';
}
