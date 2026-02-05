// Authentication types
export interface User {
  id: number;
  username: string;
  role: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// Stream types
export interface ActiveStream {
  session_id: string;
  user_name: string;
  media_title: string;
  display_title: string;
  stream_bitrate_mbps: number;    // Media file's encoded bitrate
  stream_bandwidth_mbps: number;  // Actual network throughput
  quality_profile?: string;
  transcode_decision?: string;
  state: string;
  player?: string;
  platform?: string;
  is_lan?: boolean;
}

export interface StreamReservation {
  id: string;
  user_id: string;
  user_name: string;
  media_title: string;
  player: string;
  bandwidth_mbps: number;
  expires_at: string;
  remaining_seconds: number;
}

export interface ActiveStreamsResponse {
  active_streams: ActiveStream[];
  total_streams: number;
  total_bandwidth_mbps: number;
  reservations: StreamReservation[];
  total_reserved_mbps: number;
}

export interface StreamHistory {
  id: number;
  session_id: string;
  user_name: string;
  media_title: string;
  display_title: string;
  started_at: string;
  ended_at: string;
  stream_bandwidth_mbps: number;
  quality_profile?: string;
  transcode_decision?: string;
}

export interface StreamsHistoryResponse {
  streams: StreamHistory[];
  total: number;
  page: number;
  page_size: number;
}

export interface StreamSummary {
  total_streams: number;
  unique_users: number;
  total_bandwidth_gb: number;
  avg_bandwidth_mbps: number;
  min_bandwidth_mbps: number;
  peak_individual_bandwidth_mbps: number;
  peak_combined_bandwidth_mbps: number;
  avg_stream_duration_minutes: number;
  total_duration_hours: number;
  days: number;
  most_common_quality: string;
}

// Bandwidth types
export interface BandwidthInfo {
  total_limit: number;
  qbittorrent_speed: number | null;
  qbittorrent_limit: number | null;
  sabnzbd_speed: number | null;
  sabnzbd_limit: number | null;
  snmp_speed: number | null;
  available: number;
  current_usage: number;
  used: number;
  utilization_percent: number;
}

export interface StreamInfo {
  active_count: number;
  total_bandwidth_mbps: number;
  reserved_bandwidth_mbps: number;
}

export interface CurrentBandwidthResponse {
  timestamp: string;
  download: BandwidthInfo;
  upload: BandwidthInfo;
  streams: StreamInfo;
}

export interface BandwidthMetric {
  timestamp: string;
  total_download_limit: number;
  qbittorrent_download_speed: number | null;
  qbittorrent_download_limit: number | null;
  sabnzbd_download_speed: number | null;
  sabnzbd_download_limit: number | null;
  total_upload_limit: number;
  qbittorrent_upload_speed: number | null;
  qbittorrent_upload_limit: number | null;
  sabnzbd_upload_speed: number | null;
  sabnzbd_upload_limit: number | null;
  snmp_download_speed: number | null;
  snmp_upload_speed: number | null;
  active_streams_count: number;
  total_stream_bandwidth: number;
  is_throttled: boolean;
}

export interface BandwidthHistoryResponse {
  metrics: BandwidthMetric[];
  total: number;
}

export interface BandwidthSummary {
  current_download_speed: number;
  current_upload_speed: number;
  avg_download_speed_1h: number;
  avg_upload_speed_1h: number;
  avg_download_speed_24h: number;
  avg_upload_speed_24h: number;
  peak_download_speed_24h: number;
  peak_upload_speed_24h: number;
  total_data_download_24h_gb: number;
  total_data_upload_24h_gb: number;
}

export interface ChartDataPoint {
  timestamp: string;
  download_speed: number;
  upload_speed: number;
  stream_bandwidth: number;
  // Per-client download speeds
  qbittorrent_speed: number;
  sabnzbd_speed: number;
  nzbget_speed: number;
  transmission_speed: number;
  deluge_speed: number;
  // Per-client upload speeds
  qbittorrent_upload_speed: number;
  transmission_upload_speed: number;
  deluge_upload_speed: number;
  // Per-client download limits
  qbittorrent_download_limit: number | null;
  sabnzbd_download_limit: number | null;
  nzbget_download_limit: number | null;
  transmission_download_limit: number | null;
  deluge_download_limit: number | null;
  // Per-client upload limits
  qbittorrent_upload_limit: number | null;
  transmission_upload_limit: number | null;
  deluge_upload_limit: number | null;
  // Other
  active_streams_count: number;
  snmp_download_speed: number | null;
  snmp_upload_speed: number | null;
}

export interface BandwidthChartDataResponse {
  data: ChartDataPoint[];
  start_time: string;
  end_time: string;
  interval_minutes: number;
}

// Client status for bandwidth cards
export interface ClientBandwidthStatus {
  type: string;
  name: string;
  color: string;
  speed: number;
  limit: number;
  active: boolean;
  error?: string | null;
}

// Status types
export interface SystemStatus {
  status: string;
  active_streams: number;
  is_throttled: boolean;
  monitoring_enabled: boolean;
  setup_required?: boolean;
  snmp_enabled?: boolean;
  plex_status?: { connected: boolean; consecutive_failures: number };
  snmp_status?: { enabled: boolean; connected: boolean };
  clients: {
    qbittorrent: boolean;
    sabnzbd: boolean;
    plex: boolean;
  };
  bandwidth: {
    download: {
      total_limit: number;
      current_usage: number;
      available: number;
      clients?: ClientBandwidthStatus[];
      qbittorrent_speed?: number | null;
      qbittorrent_limit?: number | null;
      sabnzbd_speed?: number | null;
      sabnzbd_limit?: number | null;
      snmp_speed?: number | null;
    };
    upload: {
      total_limit: number;
      current_usage: number;
      available: number;
      clients?: ClientBandwidthStatus[];
      qbittorrent_speed?: number | null;
      qbittorrent_limit?: number | null;
      snmp_speed?: number | null;
      stream_bandwidth?: number | null;
      reserved_bandwidth?: number | null;
      holding_bandwidth?: number | null;
    };
  };
}

// Control types
export interface RestoreSpeedsResponse {
  message: string;
  qbittorrent_restored: boolean;
  sabnzbd_restored: boolean;
}

export interface ManualThrottleRequest {
  download_limit?: number;
  upload_limit?: number;
  reason?: string;
}

export interface ManualThrottleResponse {
  message: string;
  applied_limits: {
    qbittorrent_download?: number;
    qbittorrent_upload?: number;
    sabnzbd_download?: number;
    sabnzbd_upload?: number;
  };
}

export interface MonitoringControlResponse {
  message: string;
  monitoring_enabled: boolean;
}

// Settings types
export interface SettingsSectionsResponse {
  sections: string[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface SettingsSectionResponse<T = any> {
  section: string;
  config: T;
}

export interface SettingsUpdateResponse {
  success: boolean;
  message: string;
  section: string;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
  details?: Record<string, unknown>;
}

export interface ExportYAMLResponse {
  yaml: string;
  timestamp: string;
}

export interface ConfigHistoryEntry {
  id: number;
  key: string;
  old_value: string | null;
  new_value: string;
  value_type: string;
  changed_at: string;
  changed_by: number | null;
  user_email?: string;
}

// ConfigHistory API returns array directly
export type ConfigHistoryResponse = ConfigHistoryEntry[];

// SNMP types
export interface SNMPInterface {
  index: number;
  name: string;
  description: string;
  type: string;
  speed_mbps?: number;
  admin_status?: string;
  oper_status?: string;
  speed?: number;
  status?: string;
  is_wan_candidate?: boolean;
  in_gb?: number;
  out_gb?: number;
  in_octets?: number;
  out_octets?: number;
  last_poll?: string;
  in_speed_mbps?: number;
  out_speed_mbps?: number;
  current_in_mbps?: number;
  current_out_mbps?: number;
}

export interface SNMPDiscoverResponse {
  success: boolean;
  interfaces: SNMPInterface[];
  suggested_wan?: string | null;
  message?: string;
}

export interface SNMPSpeedResponse {
  success: boolean;
  download_mbps?: number | null;
  upload_mbps?: number | null;
  speeds?: Record<string, {
    current_in_mbps: number;
    current_out_mbps: number;
  }>;
  interface_data?: Record<string, {
    in_speed_mbps: number;
    out_speed_mbps: number;
  }>;
  message?: string;
}

// Decision log types
export interface DecisionLogEntry {
  id: number;
  timestamp: string;
  active_streams: number;
  stream_bandwidth_mbps: number;
  reserved_bandwidth_mbps: number;
  available_upload_mbps: number;
  decision: string;
  changes_made: boolean;
  details: Record<string, unknown>;
}

export interface DecisionLogsResponse {
  logs: DecisionLogEntry[];
  total: number;
  days: number;
  limit: number;
  offset: number;
}
