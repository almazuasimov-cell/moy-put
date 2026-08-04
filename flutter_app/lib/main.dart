/// «Мой путь» — AI Voice Diary
/// Точка входа приложения
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_service.dart';
import 'auth_screen.dart';
import 'home_screen.dart';
import 'onboarding_screen.dart';
import 'update_screen.dart';
import 'notification_service.dart';
import 'config.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(systemNavigationBarColor: Colors.transparent),
  );
  runApp(const MyApp());
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  bool _initialized = false;
  bool _isLoggedIn = false;
  bool _showOnboarding = false;
  Map<String, dynamic>? _updateInfo;

  @override
  void initState() {
    super.initState();
    _initApp();
  }

  Future<void> _initApp() async {
    await ApiService.init();
    await NotificationService.init();
    final prefs = await SharedPreferences.getInstance();
    final onboardingDone = prefs.getBool(AppConfig.onboardingDoneKey) ?? false;

    // Проверка обновления
    Map<String, dynamic>? updateInfo;
    try {
      final info = await PackageInfo.fromPlatform();
      final currentCode = int.tryParse(info.buildNumber) ?? 0;
      final skippedVersion = prefs.getInt(AppConfig.skippedVersionKey) ?? 0;

      // Сохраняем текущую версию как установленную при первом запуске
      final installedVersion = prefs.getInt(AppConfig.installedVersionKey) ?? 0;
      if (installedVersion == 0 || currentCode > installedVersion) {
        await prefs.setInt(AppConfig.installedVersionKey, currentCode);
      }

      final serverInfo = await ApiService.checkUpdate();
      if (serverInfo.isNotEmpty) {
        final serverCode = serverInfo['version_code'] ?? 0;
        final isRequired = serverInfo['is_required'] ?? false;

        if (serverCode > currentCode && serverCode != skippedVersion && isRequired) {
          updateInfo = serverInfo;
        }
      }
    } catch (_) {}

    if (!mounted) return;
    setState(() {
      _isLoggedIn = ApiService.isLoggedIn;
      _showOnboarding = !onboardingDone && !_isLoggedIn;
      _updateInfo = updateInfo;
      _initialized = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: _buildTheme(Brightness.light),
      darkTheme: _buildTheme(Brightness.dark),
      themeMode: ThemeMode.system,
      home: !_initialized
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _updateInfo != null
              ? UpdateScreen(
                  updateInfo: _updateInfo!,
                  forceUpdate: _updateInfo!['is_required'] ?? false,
                )
              : _showOnboarding
                  ? const OnboardingScreen()
                  : _isLoggedIn
                      ? const HomeScreen()
                      : const AuthScreen(),
    );
  }

  ThemeData _buildTheme(Brightness brightness) {
    final isDark = brightness == Brightness.dark;
    final seed = const Color(0xFF6750A4);
    final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: brightness);

    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      fontFamily: null,
      appBarTheme: AppBarTheme(
        centerTitle: false,
        backgroundColor: scheme.surface,
        surfaceTintColor: scheme.surfaceTint,
      ),
      cardTheme: CardThemeData(
        surfaceTintColor: scheme.surfaceTint,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
    );
  }
}
