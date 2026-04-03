class CompanyBrief {
  CompanyBrief({required this.id, required this.name, required this.docPrefix});
  final int id;
  final String name;
  final String docPrefix;

  factory CompanyBrief.fromJson(Map<String, dynamic> j) => CompanyBrief(
        id: j['id'] as int,
        name: (j['name'] ?? '') as String,
        docPrefix: (j['doc_prefix'] ?? '') as String,
      );
}

class MeOut {
  MeOut({
    required this.id,
    required this.username,
    required this.fullName,
    required this.role,
    required this.preferredCurrency,
    required this.companies,
  });
  final int id;
  final String username;
  final String fullName;
  final String role;
  final String preferredCurrency;
  final List<CompanyBrief> companies;

  factory MeOut.fromJson(Map<String, dynamic> j) => MeOut(
        id: j['id'] as int,
        username: (j['username'] ?? '') as String,
        fullName: (j['full_name'] ?? '') as String,
        role: (j['role'] ?? '') as String,
        preferredCurrency: (j['preferred_currency'] ?? 'USD') as String,
        companies: ((j['companies'] ?? []) as List)
            .map((e) => CompanyBrief.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class SiteBrief {
  SiteBrief({
    required this.id,
    required this.projectId,
    required this.name,
    required this.status,
    required this.lat,
    required this.lng,
  });
  final int id;
  final int projectId;
  final String name;
  final String status;
  final double? lat;
  final double? lng;

  factory SiteBrief.fromJson(Map<String, dynamic> j) => SiteBrief(
        id: j['id'] as int,
        projectId: j['project_id'] as int,
        name: (j['name'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        lat: (j['lat'] as num?)?.toDouble(),
        lng: (j['lng'] as num?)?.toDouble(),
      );
}

class ScheduleItemOut {
  ScheduleItemOut({
    required this.id,
    required this.projectId,
    required this.title,
    required this.date,
    required this.startTime,
    required this.endTime,
    required this.status,
    required this.type,
    required this.siteId,
  });

  final int id;
  final int projectId;
  final String title;
  final String? date;
  final String? startTime;
  final String? endTime;
  final String status;
  final String type;
  final int? siteId;

  factory ScheduleItemOut.fromJson(Map<String, dynamic> j) => ScheduleItemOut(
        id: j['id'] as int,
        projectId: j['project_id'] as int,
        title: (j['title'] ?? '') as String,
        date: j['date'] as String?,
        startTime: j['start_time'] as String?,
        endTime: j['end_time'] as String?,
        status: (j['status'] ?? '') as String,
        type: (j['type'] ?? '') as String,
        siteId: j['site_id'] as int?,
      );
}

class LeaveTypeOut {
  LeaveTypeOut({required this.id, required this.name});
  final int id;
  final String name;
  factory LeaveTypeOut.fromJson(Map<String, dynamic> j) => LeaveTypeOut(
        id: j['id'] as int,
        name: (j['name'] ?? '') as String,
      );
}

