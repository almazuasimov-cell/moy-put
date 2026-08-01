/// Экран настроек/профиля
import 'package:flutter/material.dart';

import 'api_service.dart';
import 'config.dart';

class SettingsScreen extends StatelessWidget {
  final VoidCallback? onLogout;
  final bool isSetup;

  const SettingsScreen({super.key, this.onLogout, this.isSetup = false});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final urlController = TextEditingController(text: ApiService.apiUrl);

    return Scaffold(
      appBar: AppBar(title: Text(isSetup ? 'Настройка сервера' : 'Профиль')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Profile header
            if (!isSetup) ...[
              Center(
                child: Column(
                  children: [
                    CircleAvatar(
                      radius: 40,
                      backgroundColor: cs.primaryContainer,
                      child: Icon(Icons.person_rounded, size: 48, color: cs.primary),
                    ),
                    const SizedBox(height: 12),
                    FutureBuilder<String?>(
                      future: ApiService.getUserName(),
                      builder: (ctx, snap) => Text(
                        snap.data ?? 'Пользователь',
                        style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 32),
            ],

            // Server URL
            Text('Подключение к серверу', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            TextField(
              controller: urlController,
              decoration: InputDecoration(
                labelText: 'API URL',
                hintText: 'http://IP:8001',
                border: const OutlineInputBorder(),
                prefixIcon: const Icon(Icons.dns_rounded),
              ),
            ),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: () async {
                await ApiService.setApiUrl(urlController.text.trim());
                final ok = await ApiService.checkHealth();
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(ok ? 'Сервер доступен ✓' : 'Сервер недоступен ✗'),
                      backgroundColor: ok ? Colors.green.shade700 : Colors.red.shade700,
                    ),
                  );
                  if (ok && isSetup) {
                    Navigator.pop(context, urlController.text.trim());
                  }
                }
              },
              child: const Text('Проверить и сохранить'),
            ),
            const SizedBox(height: 32),

            // App info
            if (!isSetup) ...[
              Card(
                child: ListTile(
                  leading: Icon(Icons.info_outline, color: cs.primary),
                  title: Text(AppConfig.appName, style: const TextStyle(fontWeight: FontWeight.bold)),
                  subtitle: Text('Версия ${AppConfig.appVersion}'),
                ),
              ),
              const SizedBox(height: 16),

              // Logout
              FilledButton.tonalIcon(
                onPressed: () async {
                  final confirmed = await showDialog<bool>(
                    context: context,
                    builder: (ctx) => AlertDialog(
                      title: const Text('Выйти?'),
                      content: const Text('Потребуется снова войти.'),
                      actions: [
                        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Отмена')),
                        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Выйти')),
                      ],
                    ),
                  );
                  if (confirmed == true && onLogout != null) {
                    onLogout!();
                  }
                },
                icon: const Icon(Icons.logout_rounded),
                label: const Text('Выйти из аккаунта'),
                style: FilledButton.styleFrom(backgroundColor: cs.errorContainer),
              ),
            ],
          ],
        ),
      ),
    );
  }
}