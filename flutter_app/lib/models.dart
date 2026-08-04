/// Модели данных для «Мой путь»
import 'dart:convert';

class DiaryEntry {
  final int? id;
  final int? userId;
  final String transcriptText;
  final String structuredText;
  final int mood;
  final List<String> tags;
  final List<String> topics;
  final String aiSummary;
  final String reflection;
  final String? createdAt;
  final String? updatedAt;

  DiaryEntry({
    this.id,
    this.userId,
    required this.transcriptText,
    this.structuredText = '',
    this.mood = 5,
    this.tags = const [],
    this.topics = const [],
    this.aiSummary = '',
    this.reflection = '',
    this.createdAt,
    this.updatedAt,
  });

  factory DiaryEntry.fromJson(Map<String, dynamic> json) {
    return DiaryEntry(
      id: json['id'] as int?,
      userId: json['user_id'] as int?,
      transcriptText: (json['transcript_text'] ?? '') as String,
      structuredText: (json['structured_text'] ?? '') as String,
      mood: (json['mood'] ?? 5) as int,
      tags: _parseList(json['tags']),
      topics: _parseList(json['topics']),
      aiSummary: (json['ai_summary'] ?? '') as String,
      reflection: (json['reflection'] ?? '') as String,
      createdAt: json['created_at'] as String?,
      updatedAt: json['updated_at'] as String?,
    );
  }

  static List<String> _parseList(dynamic val) {
    if (val == null) return [];
    if (val is List) return val.map((e) => e.toString()).toList();
    if (val is String) {
      try {
        final decoded = jsonDecode(val);
        if (decoded is List) return decoded.map((e) => e.toString()).toList();
      } catch (_) {}
    }
    return [];
  }

  Map<String, dynamic> toJson() => {
    'transcript_text': transcriptText,
    'structured_text': structuredText,
    'mood': mood,
    'tags': tags,
    'topics': topics,
    'ai_summary': aiSummary,
    'reflection': reflection,
  };

  String get formattedDate {
    if (createdAt == null || createdAt!.isEmpty) return '';
    try {
      final dt = DateTime.parse(createdAt!).toLocal();
      return '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')}.${dt.year}';
    } catch (_) {
      return createdAt!;
    }
  }

  String get formattedTime {
    if (createdAt == null || createdAt!.isEmpty) return '';
    try {
      final dt = DateTime.parse(createdAt!).toLocal();
      return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return '';
    }
  }
}

class ProcessResult {
  final int mood;
  final List<String> tags;
  final List<String> topics;
  final String structuredText;
  final String aiSummary;
  final String reflection;

  ProcessResult({
    required this.mood,
    this.tags = const [],
    this.topics = const [],
    this.structuredText = '',
    this.aiSummary = '',
    this.reflection = '',
  });

  factory ProcessResult.fromJson(Map<String, dynamic> json) {
    return ProcessResult(
      mood: (json['mood'] ?? 5) as int,
      tags: _parseTags(json['tags']),
      topics: _parseTags(json['topics']),
      structuredText: (json['structured_text'] ?? '') as String,
      aiSummary: (json['ai_summary'] ?? '') as String,
      reflection: (json['reflection'] ?? '') as String,
    );
  }

  static List<String> _parseTags(dynamic val) {
    if (val == null) return [];
    if (val is List) return val.map((e) => e.toString()).toList();
    return [];
  }
}

class Stats {
  final int totalEntries;
  final int periodEntries;
  final double avgMood;
  final List<MoodPoint> moodTrend;
  final List<TagCount> topTags;
  final int streak;

  Stats({
    this.totalEntries = 0,
    this.periodEntries = 0,
    this.avgMood = 0,
    this.moodTrend = const [],
    this.topTags = const [],
    this.streak = 0,
  });

  factory Stats.fromJson(Map<String, dynamic> json) {
    return Stats(
      totalEntries: (json['total_entries'] ?? 0) as int,
      periodEntries: (json['period_entries'] ?? 0) as int,
      avgMood: (json['avg_mood'] ?? 0).toDouble(),
      moodTrend: ((json['mood_trend'] ?? []) as List)
          .map((e) => MoodPoint.fromJson(e as Map<String, dynamic>))
          .toList(),
      topTags: ((json['top_tags'] ?? []) as List)
          .map((e) => TagCount.fromJson(e as Map<String, dynamic>))
          .toList(),
      streak: (json['streak'] ?? 0) as int,
    );
  }

  Map<String, dynamic> toJson() => {
    'total_entries': totalEntries,
    'period_entries': periodEntries,
    'avg_mood': avgMood,
    'mood_trend': moodTrend.map((e) => e.toJson()).toList(),
    'top_tags': topTags.map((e) => e.toJson()).toList(),
    'streak': streak,
  };
}

class MoodPoint {
  final String date;
  final int mood;

  MoodPoint({required this.date, required this.mood});

  factory MoodPoint.fromJson(Map<String, dynamic> json) {
    return MoodPoint(
      date: (json['date'] ?? '') as String,
      mood: (json['mood'] ?? 5) as int,
    );
  }

  Map<String, dynamic> toJson() => {'date': date, 'mood': mood};
}

class TagCount {
  final String tag;
  final int count;

  TagCount({required this.tag, required this.count});

  factory TagCount.fromJson(Map<String, dynamic> json) {
    return TagCount(
      tag: (json['tag'] ?? '') as String,
      count: (json['count'] ?? 0) as int,
    );
  }

  Map<String, dynamic> toJson() => {'tag': tag, 'count': count};
}

class ReferralInfo {
  final String code;
  final int balance;
  final int invitedCount;
  final List<ReferralItem> referrals;

  ReferralInfo({
    required this.code,
    this.balance = 0,
    this.invitedCount = 0,
    this.referrals = const [],
  });

  factory ReferralInfo.fromJson(Map<String, dynamic> json) {
    return ReferralInfo(
      code: (json['code'] ?? '') as String,
      balance: (json['balance'] ?? 0) as int,
      invitedCount: (json['invited_count'] ?? 0) as int,
      referrals: ((json['referrals'] ?? []) as List)
          .map((e) => ReferralItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class ReferralItem {
  final String name;
  final String date;
  final int bonus;

  ReferralItem({required this.name, this.date = '', this.bonus = 0});

  factory ReferralItem.fromJson(Map<String, dynamic> json) {
    return ReferralItem(
      name: (json['name'] ?? '') as String,
      date: (json['date'] ?? '') as String,
      bonus: (json['bonus'] ?? 0) as int,
    );
  }
}