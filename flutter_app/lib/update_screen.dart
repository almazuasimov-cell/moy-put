/// Экран обновления приложения
import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:open_filex/open_filex.dart';
import 'config.dart';
import 'api_service.dart';

class UpdateScreen extends StatefulWidget {
  final Map<String, dynamic> updateInfo;
  final bool forceUpdate;

  const UpdateScreen({
    super.key,
    required this.updateInfo,
    this.forceUpdate = false,
  });

  @override
  State<UpdateScreen> createState() => _UpdateScreenState();
}

class _UpdateScreenState extends State<UpdateScreen> {
  double _progress = 0;
  bool _downloading = false;
  bool _installFailed = false;
  String? _filePath;

  String get _version => widget.updateInfo['version'] ?? '';
  String get _changelog => widget.updateInfo['changelog'] ?? '';
  String get _apkUrl => widget.updateInfo['apk_url'] ?? '';

  @override
  void initState() {
    super.initState();
    if (widget.forceUpdate) {
      _startDownload();
    }
  }

  Future<void> _startDownload() async {
    if (_apkUrl.isEmpty) {
      if (mounted) setState(() => _installFailed = true);
      return;
    }

    setState(() => _downloading = true);

    try {
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/moy_put_update.apk');
      _filePath = file.path;

      final response = await http.get(Uri.parse(_apkUrl));
      await file.writeAsBytes(response.bodyBytes);

      if (mounted) {
        setState(() {
          _downloading = false;
          _progress = 1.0;
        });
        await _install();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _downloading = false;
          _installFailed = true;
        });
      }
    }
  }

  Future<void> _install() async {
    if (_filePath == null) return;
    try {
      await OpenFilex.open(_filePath!);
      // Ждём и проверяем установку
      await Future.delayed(const Duration(seconds: 3));
      await _verifyInstallation();
    } catch (e) {
      if (mounted) setState(() => _installFailed = true);
    }
  }

  Future<void> _verifyInstallation() async {
    try {
      final info = await PackageInfo.fromPlatform();
      final currentCode = int.tryParse(info.buildNumber) ?? 0;
      final serverCode = widget.updateInfo['version_code'] ?? 0;

      if (currentCode >= serverCode) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setInt(AppConfig.installedVersionKey, serverCode);
        if (mounted) {
          Navigator.of(context).pushReplacementNamed('/');
        }
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.system_update, size: 64, color: scheme.primary),
              const SizedBox(height: 24),
              Text(
                'Доступно обновление',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                'Версия $_version',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: scheme.primary,
                    ),
              ),
              if (_changelog.isNotEmpty) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: scheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    _changelog,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
              ],
              const SizedBox(height: 32),
              if (_downloading) ...[
                LinearProgressIndicator(value: _progress),
                const SizedBox(height: 8),
                Text('Загрузка... ${(_progress * 100).toInt()}%'),
              ] else if (_installFailed) ...[
                Text(
                  'Не удалось установить обновление',
                  style: TextStyle(color: scheme.error),
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _startDownload,
                  child: const Text('Попробовать снова'),
                ),
              ] else ...[
                FilledButton.icon(
                  onPressed: _startDownload,
                  icon: const Icon(Icons.download),
                  label: const Text('Скачать и установить'),
                ),
              ],
              if (!widget.forceUpdate) ...[
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () async {
                    final prefs = await SharedPreferences.getInstance();
                    await prefs.setInt(
                      AppConfig.skippedVersionKey,
                      widget.updateInfo['version_code'] ?? 0,
                    );
                    if (mounted) {
                      Navigator.of(context).pushReplacementNamed('/');
                    }
                  },
                  child: const Text('Позже'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
